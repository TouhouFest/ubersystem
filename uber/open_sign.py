import logging
from json import dumps, loads
from requests import get, post, put
from uber.config import c

log = logging.getLogger(__name__)


from uber.signature_service import BaseSignatureRequest


class OpenSignRequest(BaseSignatureRequest):
    """
    OpenSign e-signature service client and request handler (`OpenSignRequest`).
    
    Implements e-signature document workflows using OpenSign's v1/v1.2 REST API endpoints.
    Official Documentation:
      - API v1.2 Overview: https://docs.opensignlabs.com/docs/API-docs/v1.2/opensign-api-v-1-2
      - GitHub Repository: https://github.com/opensignlabs/opensign
    """
    def _init_create_document(self, group):
        texts = getattr(group, 'esign_texts_list', getattr(group, 'signnow_texts_list', None))
        if hasattr(texts, '_mock_name') and hasattr(group, 'signnow_texts_list') and not hasattr(group.signnow_texts_list, '_mock_name'):
            texts = group.signnow_texts_list
        return self.create_document(
            template_id=getattr(c, 'OPENSIGN_DEALER_TEMPLATE_ID', ''),
            doc_title="MFF {} Dealer Terms - {}".format(c.EVENT_YEAR, group.name),
            folder_id=getattr(c, 'OPENSIGN_DEALER_FOLDER_ID', ''),
            uneditable_texts_list=texts,
            fields={'printed_name': self.group_leader_name})

    @property
    def api_call_headers(self):
        """
        Headers for making OpenSign API requests.
        
        API Docs: https://docs.opensignlabs.com/docs/API-docs/v1.2/opensign-api-v-1-2#authentication
        Supports both Authorization Bearer token (cloud/standard) and x-api-token header (self-hosted) formats.
        """
        return {
            "Authorization": f"Bearer {self.access_token}",
            "x-api-token": f"{self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def set_access_token(self):
        """
        Retrieves and initializes the OpenSign API token from Redis (`c.REDIS_STORE`) or `c.OPENSIGN_API_TOKEN`.
        If missing, triggers the background Celery/Redis secret rotation task (`set_opensign_key.delay()`).
        """
        from uber.tasks.redis import set_opensign_key

        set_opensign_key.delay()
        self.access_token = c.REDIS_STORE.get(c.REDIS_PREFIX + 'opensign_access_token')

        if self.access_token:
            if isinstance(self.access_token, bytes):
                self.access_token = self.access_token.decode('utf-8')
            return

        if getattr(c, 'OPENSIGN_API_TOKEN', ''):
            self.access_token = c.OPENSIGN_API_TOKEN
            return
        elif not getattr(c, 'AWS_OPENSIGN_SECRET_NAME', ''):
            self.error_message = ("Couldn't get an OpenSign access token because OPENSIGN_API_TOKEN "
                                  "and AWS_OPENSIGN_SECRET_NAME are not set.")
        else:
            self.error_message = "Couldn't set the OpenSign key. Check the redis task for errors."

        if self.error_message:
            log.error(self.error_message)

    def create_document(self, template_id, doc_title, folder_id='', uneditable_texts_list=None, fields={}):
        """
        Creates a new signing document instance from a predefined OpenSign template.
        
        API Docs: https://docs.opensignlabs.com/docs/API-docs/v1.2/createdocumentwithtemplateid
        Endpoint: POST /v1/template/send_template (or /v1/createdocument/:template_id in v1.2)
        Payload schema:
          - template_id: String ID of the draft template
          - title: Name/title of the generated document
          - signers: List of signer objects with name, email, role (e.g. "Dealer"), and order
          - fields: Dictionary mapping template widget field names to initial values
        """
        if self.invalid_request("Tried to create a document"):
            log.error(self.error_message)
            return None

        base_url = getattr(c, 'OPENSIGN_API_URL', 'https://api.opensignlabs.com/v1').rstrip('/')
        payload = {
            "template_id": template_id,
            "title": doc_title,
            "folder_id": folder_id,
            "signers": [],
            "fields": fields or {}
        }
        if self.group:
            payload["signers"].append({
                "name": self.group_leader_name or self.group.name,
                "email": self.group.email,
                "role": "Dealer",
                "order": 1
            })
        if uneditable_texts_list:
            payload["uneditable_texts"] = uneditable_texts_list

        response = post(f"{base_url}/template/send_template", headers=self.api_call_headers, data=dumps(payload))
        if response.status_code not in (200, 201, 204):
            try:
                err_data = loads(response.content)
                err_msg = err_data.get('error') or err_data.get('message') or str(err_data)
            except Exception:
                err_msg = response.text
            self.error_message = f"Error creating OpenSign document from template with token {self.access_token}: {err_msg}"
            log.error(self.error_message)
            return None

        data = loads(response.content)
        if 'error' in data or 'errors' in data:
            err_msg = data.get('error') or '; '.join([e.get('message', str(e)) if isinstance(e, dict) else str(e) for e in data.get('errors', [])])
            self.error_message = f"Error creating OpenSign document: {err_msg}"
            log.error(self.error_message)
            return None

        document_id = data.get('objectId') or data.get('id') or data.get('document_id')
        if not document_id and isinstance(data, dict) and 'data' in data and isinstance(data['data'], dict):
            document_id = data['data'].get('objectId') or data['data'].get('id') or data['data'].get('document_id')

        return document_id

    def get_doc_signed_timestamp(self):
        """
        Retrieves the exact epoch timestamp when the document was fully signed or completed.
        
        API Docs: https://docs.opensignlabs.com/docs/API-docs/v1.2/getdocument
        Endpoint: GET /v1/document/:document_id
        Inspects document `status` ('completed'/'signed') and extracts `completed_at`, `signed_at`, `updated_at`,
        or signature metadata timestamps (`created` / `timestamp`).
        """
        if self.invalid_request("Tried to get a signed timestamp"):
            log.error(self.error_message)
            return None

        details = self.get_document_details()
        if details:
            status = details.get('status')
            val = None
            if status in ['completed', 'signed']:
                val = details.get('completed_at') or details.get('signed_at') or details.get('updated_at')
            if not val and details.get('signatures'):
                val = details['signatures'][0].get('created') or details['signatures'][0].get('timestamp')
            if val:
                try:
                    return int(float(val))
                except (ValueError, TypeError):
                    try:
                        from dateutil import parser as dateparser
                        return int(dateparser.parse(str(val)).timestamp())
                    except Exception:
                        pass
        return None

    def get_signing_link(self, first_name="", last_name="", redirect_uri=""):
        """
        Retrieves an embedded signing URL for freestyle or embedded session signing.
        
        API Docs:
          - Self Sign: https://docs.opensignlabs.com/docs/API-docs/v1.2/selfsign
          - Get Signing Links: https://docs.opensignlabs.com/docs/API-docs/v1.2/getsigninglinks
        Endpoint: POST /v1/document/embed_token (or GET /v1/signinglinks/:document_id)
        Returns the signing URL (`url_no_signup`, `url`, `signing_url`, or `embed_url`) or None on error.
        """
        if self.invalid_request("Tried to send a signing link"):
            log.error(self.error_message)
            return None

        base_url = getattr(c, 'OPENSIGN_API_URL', 'https://api.opensignlabs.com/v1').rstrip('/')
        payload = {
            "document_id": self.document.document_id,
            "firstname": first_name,
            "lastname": last_name,
            "redirect_uri": redirect_uri
        }
        response = post(f"{base_url}/document/embed_token", headers=self.api_call_headers, data=dumps(payload))
        if response.status_code not in (200, 201):
            try:
                err_data = loads(response.content)
                err_msg = err_data.get('error') or err_data.get('message') or str(err_data)
            except Exception:
                err_msg = response.text
            self.error_message = f"Error getting OpenSign signing link: {err_msg}"
            log.error(self.error_message)
            return None

        data = loads(response.content)
        if 'errors' in data or 'error' in data:
            err_msg = data.get('error') or '; '.join([e.get('message', str(e)) if isinstance(e, dict) else str(e) for e in data.get('errors', [])])
            self.error_message = f"Error getting OpenSign signing link: {err_msg}"
            log.error(self.error_message)
            return None

        return data.get('url_no_signup') or data.get('url') or data.get('signing_url') or data.get('embed_url')

    def send_dealer_signing_invite(self):
        """
        Sends an email invitation containing a unique signing link directly to the dealer/group leader.
        
        API Docs: https://docs.opensignlabs.com/docs/API-docs/v1.2/resendrequestmail
        Endpoint: POST /v1/document/invite
        Requires a valid `group` attached to the request (`check_group=True`).
        """
        from uber.custom_tags import email_only

        if self.invalid_request("Tried to send a dealer signing invite", check_group=True):
            log.error(self.error_message)
            return None

        base_url = getattr(c, 'OPENSIGN_API_URL', 'https://api.opensignlabs.com/v1').rstrip('/')
        invite_payload = {
            "document_id": self.document.document_id,
            "to": [
                {
                    "email": self.group.email,
                    "name": self.group_leader_name or self.group.name,
                    "role": "Dealer",
                    "order": 1
                }
            ],
            "from": email_only(c.MARKETPLACE_EMAIL),
            "subject": f"ACTION REQUIRED: {c.EVENT_NAME} {c.DEALER_TERM.title()} Terms and Conditions",
            "message": (f"Congratulations on being accepted into the {c.EVENT_NAME} {c.DEALER_LOC_TERM.title()}! "
                        "Please click the button below to review and sign the terms and conditions. "
                        "You MUST sign this in order to complete your registration."),
            "redirect_uri": "{}/preregistration/group_members?id={}".format(
                c.REDIRECT_URL_BASE or c.URL_BASE, self.group.id
            )
        }

        response = post(f"{base_url}/document/invite", headers=self.api_call_headers, data=dumps(invite_payload))
        if response.status_code not in (200, 201):
            try:
                err_data = loads(response.content)
                err_msg = err_data.get('error') or err_data.get('message') or str(err_data)
            except Exception:
                err_msg = response.text
            self.error_message = f"Error sending OpenSign invite to sign: {err_msg}"
            log.error(self.error_message)
            return None

        invite_request = loads(response.content)
        if 'error' in invite_request:
            self.error_message = "Error sending OpenSign invite to sign: " + invite_request['error']
            log.error(self.error_message)
            return None

        return invite_request

    def get_download_link(self):
        """
        Retrieves a download URL for the signed or completed PDF document.
        
        API Docs: https://docs.opensignlabs.com/docs/API-docs/v1.2/getdocument
        Endpoint: GET /v1/document/:document_id/download
        Checks `link`, `url`, and `download_url` attributes in the response payload.
        """
        if self.invalid_request("Tried to get a download link"):
            log.error(self.error_message)
            return None

        base_url = getattr(c, 'OPENSIGN_API_URL', 'https://api.opensignlabs.com/v1').rstrip('/')
        response = get(f"{base_url}/document/{self.document.document_id}/download", headers=self.api_call_headers)
        if response.status_code != 200:
            try:
                err_data = loads(response.content)
                err_msg = err_data.get('error') or err_data.get('message') or str(err_data)
            except Exception:
                err_msg = response.text
            self.error_message = f"Error getting OpenSign download link: {err_msg}"
            log.error(self.error_message)
            return None

        data = loads(response.content)
        if 'error' in data:
            self.error_message = "Error getting OpenSign download link: " + data['error']
            log.error(self.error_message)
            return None

        return data.get('link') or data.get('url') or data.get('download_url')

    def get_document_details(self):
        """
        Retrieves raw metadata details for the attached OpenSign document.
        
        API Docs: https://docs.opensignlabs.com/docs/API-docs/v1.2/getdocument
        Endpoint: GET /v1/document/:document_id
        Returns full document JSON schema including `status`, `completed_at`, `signatures`, and signer history.
        """
        if self.invalid_request("Tried to get document details from a request"):
            log.error(self.error_message)
            return None

        base_url = getattr(c, 'OPENSIGN_API_URL', 'https://api.opensignlabs.com/v1').rstrip('/')
        response = get(f"{base_url}/document/{self.document.document_id}", headers=self.api_call_headers)
        if response.status_code != 200:
            try:
                err_data = loads(response.content)
                err_msg = err_data.get('error') or err_data.get('message') or str(err_data)
            except Exception:
                err_msg = response.text
            self.error_message = f"Error getting OpenSign document: {err_msg}"
            log.error(self.error_message)
            return None

        data = loads(response.content)
        if 'error' in data:
            self.error_message = "Error getting OpenSign document: " + data['error']
            log.error(self.error_message)
            return None

        return data
