from abc import ABC, abstractmethod
import logging
from uber.config import c

log = logging.getLogger(__name__)


class BaseSignatureRequest(ABC):
    """
    Abstract base class for e-signature service integrations (e.g. SignNowRequest, OpenSignRequest).
    Establishes a unified interface and shared behavior for managing SignedDocument records,
    checking API access tokens, and handling embedded signing flows.
    """
    def __init__(self, session, group=None, ident='', create_if_none=False):
        self.group = group
        self.group_leader_name = ''
        self.document = None
        self.access_token = None
        self.error_message = ''

        self.set_access_token()
        if self.error_message:
            log.error(self.error_message)
            return

        from uber.models import SignedDocument

        if group:
            self.document = session.query(SignedDocument).filter_by(model="Group", fk_id=group.id).first()

            if not self.document and create_if_none:
                self.document = SignedDocument(fk_id=group.id, model="Group", ident=ident)
                first_name = group.leader.first_name if group.leader else ''
                last_name = group.leader.last_name if group.leader else ''
                self.group_leader_name = (first_name + ' ' + last_name).strip()

            if self.document and not self.document.document_id:
                self.document.document_id = self._init_create_document(group)

    @property
    @abstractmethod
    def api_call_headers(self):
        """Headers dictionary for making requests to the e-signature API."""
        pass

    @abstractmethod
    def set_access_token(self):
        """Retrieve and set self.access_token from cache or configuration."""
        pass

    @abstractmethod
    def _init_create_document(self, group):
        """Helper called by __init__ to create a document from template for a group."""
        pass

    def invalid_request(self, msg, check_group=False):
        if check_group:
            if not self.group:
                self.error_message = f"{msg} without a group attached to the request!"
        elif not self.document:
            self.error_message = f"{msg} without a document attached to the request!"
        else:
            self.check_access_token(msg)
        return bool(self.error_message)

    def check_access_token(self, msg):
        if not self.access_token:
            self.set_access_token()
            if not self.access_token:
                self.error_message = f"{msg} but access token is not set!"

    @abstractmethod
    def create_document(self, template_id, doc_title, folder_id='', uneditable_texts_list=None, fields={}):
        """Create a new signing document from a template."""
        pass

    @abstractmethod
    def get_doc_signed_timestamp(self):
        """Return the Unix epoch seconds timestamp when the document was signed, or None."""
        pass

    def create_dealer_signing_link(self):
        """
        Shared method to create an embedded signing link for the attached dealer group leader,
        redirecting back to group members page once complete.
        """
        if self.invalid_request("Tried to send a dealer signing link", check_group=True):
            log.error(self.error_message)
            return None

        first_name = self.group.leader.first_name if self.group.leader else ''
        last_name = self.group.leader.last_name if self.group.leader else ''

        if self.document.document_id and not self.document.signed:
            redirect_uri = "{}/preregistration/group_members?id={}".format(
                c.REDIRECT_URL_BASE or c.URL_BASE, self.group.id
            )
            link = self.get_signing_link(first_name, last_name, redirect_uri)
            return link
        return None

    @abstractmethod
    def get_signing_link(self, first_name="", last_name="", redirect_uri=""):
        """Get an embedded signing URL for the document."""
        pass

    @abstractmethod
    def send_dealer_signing_invite(self):
        """Send an email invitation to the dealer group leader to sign the document."""
        pass

    @abstractmethod
    def get_download_link(self):
        """Get a direct download URL for the signed document."""
        pass

    @abstractmethod
    def get_document_details(self):
        """Fetch details/metadata for the document from the API."""
        pass


def get_esign_request(session, group=None, **kwargs):
    """
    Factory function returning the active e-signature service client instance (`OpenSignRequest` or `SignNowRequest`)
    based on configured template IDs (`c.OPENSIGN_DEALER_TEMPLATE_ID`).
    """
    from uber.open_sign import OpenSignRequest
    from uber.utils import SignNowRequest

    if getattr(c, 'OPENSIGN_DEALER_TEMPLATE_ID', ''):
        return OpenSignRequest(session=session, group=group, **kwargs)
    return SignNowRequest(session=session, group=group, **kwargs)
