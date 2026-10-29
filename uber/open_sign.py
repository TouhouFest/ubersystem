import logging
from json import JSONDecodeError, dumps, loads

from requests import get, post

from uber.config import c
from uber.signature_service import BaseSignatureRequest

log = logging.getLogger(__name__)


class OpenSignRequest(BaseSignatureRequest):
    """
    OpenSign e-signature service client and request handler (`OpenSignRequest`).

    Implements e-signature document workflows using OpenSign's v1.2 REST API endpoints.
    Official Documentation:
      - API v1.2 Overview: https://docs.opensignlabs.com/docs/API-docs/v1.2/opensign-api-v-1-2
      - GitHub Repository: https://github.com/opensignlabs/opensign
    """

    @property
    def base_api_url(self):
        url = getattr(c, "OPENSIGN_API_URL", "").strip()
        if not url:
            url = "https://app.opensignlabs.com/api/v1.2"
        url = url.rstrip("/")
        if (
            not url.endswith("/api/v1.2")
            and not url.endswith("/api/v1.1")
            and not url.endswith("/v1")
        ):
            url = f"{url}/api/v1.2"
        return url

    def _init_create_document(self, group):
        texts = getattr(
            group, "esign_texts_list", getattr(group, "signnow_texts_list", None)
        )
        if (
            hasattr(texts, "_mock_name")
            and hasattr(group, "signnow_texts_list")
            and not hasattr(group.signnow_texts_list, "_mock_name")
        ):
            texts = group.signnow_texts_list
        return self.create_document(
            template_id=getattr(c, "OPENSIGN_DEALER_TEMPLATE_ID", ""),
            doc_title=f"{c.EVENT_NAME} {c.EVENT_YEAR} Dealer Terms - {group.name}",
            folder_id=getattr(c, "OPENSIGN_DEALER_FOLDER_ID", ""),
            uneditable_texts_list=texts,
            fields={"printed_name": self.group_leader_name},
        )

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
            "Accept": "application/json",
        }

    def set_access_token(self):
        """
        Retrieves and initializes the OpenSign API token from config, Redis, or AWS Secrets Manager.
        """
        # 1. Direct static token configuration
        if getattr(c, "OPENSIGN_API_TOKEN", ""):
            self.access_token = c.OPENSIGN_API_TOKEN
            return

        # 2. Redis cache
        if c.REDIS_STORE:
            token = c.REDIS_STORE.get(c.REDIS_PREFIX + "opensign_access_token")
            if token:
                self.access_token = (
                    token.decode("utf-8") if isinstance(token, bytes) else token
                )
                return

        # 3. AWS Secrets Manager secret rotation
        if getattr(c, "AWS_OPENSIGN_SECRET_NAME", ""):
            from uber.tasks.redis import set_opensign_key

            try:
                set_opensign_key()
            except (ValueError, TypeError, KeyError, RuntimeError) as e:
                log.warning("Could not synchronously fetch OpenSign secret: %s", e)
                set_opensign_key.delay()

            if c.REDIS_STORE:
                token = c.REDIS_STORE.get(c.REDIS_PREFIX + "opensign_access_token")
                if token:
                    self.access_token = (
                        token.decode("utf-8") if isinstance(token, bytes) else token
                    )
                    return

        if not self.access_token:
            if not getattr(c, "OPENSIGN_API_TOKEN", "") and not getattr(
                c, "AWS_OPENSIGN_SECRET_NAME", ""
            ):
                self.error_message = (
                    "Couldn't get an OpenSign access token because OPENSIGN_API_TOKEN "
                    "and AWS_OPENSIGN_SECRET_NAME are not set."
                )
            else:
                self.error_message = "Couldn't set the OpenSign key. Check the redis task or AWS secret for errors."

        if self.error_message:
            log.error(self.error_message)

    def create_document(
        self,
        template_id,
        doc_title,
        folder_id="",
        uneditable_texts_list=None,
        fields=None,
    ):
        """
        Creates a new signing document instance from a predefined OpenSign template.

        API Docs: https://docs.opensignlabs.com/docs/API-docs/v1.2/createdocumentwithtemplateid
        Endpoint: POST /api/v1.2/createdocument/:template_id
        """
        if self.invalid_request("Tried to create a document"):
            log.error(self.error_message)
            return None

        fields = fields or {}
        formatted_fields = []
        if isinstance(fields, dict):
            for k, v in fields.items():
                formatted_fields.append({"name": k, "default": str(v)})
        elif isinstance(fields, list):
            formatted_fields = fields

        payload = {
            "title": doc_title,
            "send_emails": True,
            "signers": [],
            "fields": formatted_fields,
        }
        if folder_id:
            payload["folder_id"] = folder_id

        if self.group:
            payload["signers"].append(
                {
                    "name": self.group_leader_name or self.group.name,
                    "email": self.group.email,
                    "role": "Dealer",
                    "signer_role": "signer",
                    "order": 1,
                }
            )
        if uneditable_texts_list:
            payload["uneditable_texts"] = uneditable_texts_list

        endpoint = f"{self.base_api_url}/createdocument/{template_id}"
        response = post(endpoint, headers=self.api_call_headers, data=dumps(payload))
        if response.status_code not in (200, 201, 204):
            try:
                err_data = loads(response.content)
                err_msg = (
                    err_data.get("error") or err_data.get("message") or str(err_data)
                )
            except JSONDecodeError:
                err_msg = response.text
            self.error_message = f"Error creating OpenSign document from template with token {self.access_token}: {err_msg}"
            log.error(self.error_message)
            return None

        data = loads(response.content)
        if "error" in data or "errors" in data:
            err_msg = data.get("error") or "; ".join(
                [
                    e.get("message", str(e)) if isinstance(e, dict) else str(e)
                    for e in data.get("errors", [])
                ]
            )
            self.error_message = f"Error creating OpenSign document: {err_msg}"
            log.error(self.error_message)
            return None

        document_id = None
        if isinstance(data, dict):
            document_id = (
                data.get("objectId") or data.get("id") or data.get("document_id")
            )
            if not document_id and "data" in data and isinstance(data["data"], dict):
                document_id = (
                    data["data"].get("objectId")
                    or data["data"].get("id")
                    or data["data"].get("document_id")
                )

        return document_id

    def get_document_details(self):
        """
        Retrieves raw metadata details for the attached OpenSign document.

        API Docs: https://docs.opensignlabs.com/docs/API-docs/v1.2/getdocument
        Endpoint: GET /api/v1.2/document/:document_id
        """
        if self.invalid_request("Tried to get document details from a request"):
            log.error(self.error_message)
            return None

        endpoint = f"{self.base_api_url}/document/{self.document.document_id}"
        response = get(endpoint, headers=self.api_call_headers)
        if response.status_code != 200:
            try:
                err_data = loads(response.content)
                err_msg = (
                    err_data.get("error") or err_data.get("message") or str(err_data)
                )
            except JSONDecodeError:
                err_msg = response.text
            self.error_message = f"Error getting OpenSign document: {err_msg}"
            log.error(self.error_message)
            return None

        data = loads(response.content)
        if "error" in data:
            self.error_message = "Error getting OpenSign document: " + str(
                data["error"]
            )
            log.error(self.error_message)
            return None

        return data

    def get_doc_signed_timestamp(self):
        """
        Retrieves the exact epoch timestamp when the document was fully signed or completed.

        API Docs: https://docs.opensignlabs.com/docs/API-docs/v1.2/getdocument
        Endpoint: GET /api/v1.2/document/:document_id
        """
        if self.invalid_request("Tried to get a signed timestamp"):
            log.error(self.error_message)
            return None

        details = self.get_document_details()
        if details:
            status = details.get("status")
            val = None
            if status in ["completed", "signed"]:
                val = (
                    details.get("completed_at")
                    or details.get("signed_at")
                    or details.get("updatedAt")
                    or details.get("updated_at")
                )
            if not val and details.get("audit_trail"):
                for entry in details["audit_trail"]:
                    if isinstance(entry, dict) and entry.get("signed"):
                        val = entry["signed"]
                        break
            if not val and details.get("signatures"):
                val = details["signatures"][0].get("created") or details["signatures"][
                    0
                ].get("timestamp")
            if val:
                try:
                    return int(float(val))
                except (ValueError, TypeError):
                    try:
                        from dateutil import parser as dateparser

                        return int(dateparser.parse(str(val)).timestamp())
                    except (ValueError, TypeError):
                        log.debug("Could not parse date timestamp: %s", val)
        return None

    def get_signing_link(self, first_name="", last_name="", redirect_uri=""):
        """
        Retrieves an embedded signing URL for the document.

        API Docs: https://docs.opensignlabs.com/docs/API-docs/v1.2/getsigninglinks
        Endpoint: GET /api/v1.2/signinglinks/:document_id
        """
        if self.invalid_request("Tried to send a signing link"):
            log.error(self.error_message)
            return None

        endpoint = f"{self.base_api_url}/signinglinks/{self.document.document_id}"
        response = get(endpoint, headers=self.api_call_headers)
        if response.status_code not in (200, 201):
            try:
                err_data = loads(response.content)
                err_msg = (
                    err_data.get("error") or err_data.get("message") or str(err_data)
                )
            except JSONDecodeError:
                err_msg = response.text
            self.error_message = f"Error getting OpenSign signing link: {err_msg}"
            log.error(self.error_message)
            return None

        data = loads(response.content)
        if "error" in data or "errors" in data:
            err_msg = data.get("error") or "; ".join(
                [
                    e.get("message", str(e)) if isinstance(e, dict) else str(e)
                    for e in data.get("errors", [])
                ]
            )
            self.error_message = f"Error getting OpenSign signing link: {err_msg}"
            log.error(self.error_message)
            return None

        if isinstance(data, dict):
            if data.get("signers") and isinstance(data["signers"], list):
                if self.group and self.group.email:
                    for s in data["signers"]:
                        if (
                            isinstance(s, dict)
                            and s.get("email", "").lower() == self.group.email.lower()
                        ):
                            return s.get("signing_url") or s.get("url")
                first_s = data["signers"][0]
                if isinstance(first_s, dict):
                    return first_s.get("signing_url") or first_s.get("url")
            return (
                data.get("signing_url")
                or data.get("url")
                or data.get("url_no_signup")
                or data.get("embed_url")
            )

        return None

    def send_dealer_signing_invite(self):
        """
        Sends or resends an email invitation containing a unique signing link to the dealer/group leader.

        API Docs: https://docs.opensignlabs.com/docs/API-docs/v1.2/resendrequestmail
        Endpoint: POST /api/v1.2/resendmail
        """
        if self.invalid_request(
            "Tried to send a dealer signing invite", check_group=True
        ):
            log.error(self.error_message)
            return None

        invite_payload = {
            "document_id": self.document.document_id,
            "email": self.group.email,
            "email_subject": f"ACTION REQUIRED: {c.EVENT_NAME} {c.DEALER_TERM.title()} Terms and Conditions",
            "email_body": (
                f"Congratulations on being accepted into the {c.EVENT_NAME} {c.DEALER_LOC_TERM.title()}! "
                "Please review and sign the terms and conditions. "
                "You MUST sign this in order to complete your registration."
            ),
        }

        endpoint = f"{self.base_api_url}/resendmail"
        response = post(
            endpoint, headers=self.api_call_headers, data=dumps(invite_payload)
        )
        if response.status_code not in (200, 201):
            try:
                err_data = loads(response.content)
                err_msg = (
                    err_data.get("error") or err_data.get("message") or str(err_data)
                )
            except JSONDecodeError:
                err_msg = response.text
            self.error_message = f"Error sending OpenSign invite to sign: {err_msg}"
            log.error(self.error_message)
            return None

        invite_request = loads(response.content)
        if "error" in invite_request:
            self.error_message = "Error sending OpenSign invite to sign: " + str(
                invite_request["error"]
            )
            log.error(self.error_message)
            return None

        return invite_request

    def get_download_link(self):
        """
        Retrieves a download URL for the signed or completed PDF document.

        API Docs: https://docs.opensignlabs.com/docs/API-docs/v1.2/getdocument
        Endpoint: GET /api/v1.2/document/:document_id
        """
        if self.invalid_request("Tried to get a download link"):
            log.error(self.error_message)
            return None

        details = self.get_document_details()
        if not details:
            return None

        return (
            details.get("file")
            or details.get("certificate")
            or details.get("link")
            or details.get("url")
            or details.get("download_url")
        )
