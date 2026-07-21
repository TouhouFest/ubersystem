from datetime import datetime
from pytz import UTC
from unittest.mock import Mock, patch
import pytest

from uber.config import c
from uber.open_sign import OpenSignRequest
from uber.models import Group


@pytest.fixture
def mock_session():
    session = Mock()
    session.query.return_value.filter_by.return_value.first.return_value = None
    return session


@pytest.fixture
def mock_group():
    group = Mock(spec=Group)
    group.id = "group-123"
    group.name = "Test Dealer Booth"
    group.email = "dealer@example.com"
    group.signnow_texts_list = [{"text": "Vendor A"}]
    group.esign_texts_list = [{"text": "Vendor A"}]
    leader = Mock()
    leader.first_name = "Jane"
    leader.last_name = "Doe"
    group.leader = leader
    return group


def test_set_access_token_from_redis(monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="redis-token-abc")))
    with patch('uber.tasks.redis.set_opensign_key.delay') as mock_delay:
        req = OpenSignRequest(mock_session)
        assert req.access_token == "redis-token-abc"
        assert not req.error_message
        mock_delay.assert_called_once()


def test_set_access_token_fallback_to_config(monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value=None)))
    monkeypatch.setattr(c, 'OPENSIGN_API_TOKEN', "config-token-xyz")
    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        assert req.access_token == "config-token-xyz"
        assert not req.error_message


def test_set_access_token_error_when_missing(monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value=None)))
    monkeypatch.setattr(c, 'OPENSIGN_API_TOKEN', "")
    monkeypatch.setattr(c, 'AWS_OPENSIGN_SECRET_NAME', "")
    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        assert not req.access_token
        assert "not set" in req.error_message


def test_init_creates_document(monkeypatch, mock_session, mock_group):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    monkeypatch.setattr(c, 'OPENSIGN_DEALER_TEMPLATE_ID', "template-abc")
    monkeypatch.setattr(c, 'OPENSIGN_DEALER_FOLDER_ID', "folder-xyz")
    monkeypatch.setattr(c, 'EVENT_YEAR', 2026)

    with patch('uber.tasks.redis.set_opensign_key.delay'), \
         patch.object(OpenSignRequest, 'create_document', return_value="opensign-doc-999") as mock_create:
        req = OpenSignRequest(mock_session, group=mock_group, ident="dealer_terms", create_if_none=True)
        assert req.document is not None
        assert req.document.fk_id == "group-123"
        assert req.document.model == "Group"
        assert req.document.ident == "dealer_terms"
        assert req.document.document_id == "opensign-doc-999"
        assert req.group_leader_name == "Jane Doe"
        mock_create.assert_called_once_with(
            template_id="template-abc",
            doc_title="MFF 2026 Dealer Terms - Test Dealer Booth",
            folder_id="folder-xyz",
            uneditable_texts_list=[{"text": "Vendor A"}],
            fields={'printed_name': "Jane Doe"}
        )


@patch('uber.open_sign.post')
def test_create_document_success(mock_post, monkeypatch, mock_session, mock_group):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    monkeypatch.setattr(c, 'OPENSIGN_API_URL', "https://api.opensignlabs.com/v1")

    mock_response = Mock(status_code=200, content=b'{"objectId": "doc-777"}')
    mock_post.return_value = mock_response

    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        req.group = mock_group
        req.group_leader_name = "Jane Doe"
        req.document = Mock()
        doc_id = req.create_document("tmpl-1", "My Title", "fld-1", fields={"key": "val"})

        assert doc_id == "doc-777"
        assert not req.error_message
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.opensignlabs.com/v1/template/send_template"
        assert kwargs["headers"]["Authorization"] == "Bearer token-123"
        assert "Jane Doe" in kwargs["data"]
        assert "dealer@example.com" in kwargs["data"]


@patch('uber.open_sign.post')
def test_get_signing_link_success(mock_post, monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    monkeypatch.setattr(c, 'OPENSIGN_API_URL', "https://api.opensignlabs.com/v1")

    mock_response = Mock(status_code=200, content=b'{"url_no_signup": "https://app.opensign.com/sign/xyz"}')
    mock_post.return_value = mock_response

    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        req.document = Mock(document_id="doc-777")
        link = req.get_signing_link("Jane", "Doe", "https://redirect.com")

        assert link == "https://app.opensign.com/sign/xyz"
        assert not req.error_message
        mock_post.assert_called_once()


@patch('uber.open_sign.post')
def test_create_dealer_signing_link(mock_post, monkeypatch, mock_session, mock_group):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    monkeypatch.setattr(c, 'URL_BASE', "https://magfest.org/uber")
    monkeypatch.setattr(c, 'REDIRECT_URL_BASE', "")

    mock_response = Mock(status_code=200, content=b'{"url_no_signup": "https://app.opensign.com/sign/123"}')
    mock_post.return_value = mock_response

    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        req.group = mock_group
        req.document = Mock(document_id="doc-777", signed=None)
        link = req.create_dealer_signing_link()

        assert link == "https://app.opensign.com/sign/123"
        args, kwargs = mock_post.call_args
        assert "https://magfest.org/uber/preregistration/group_members?id=group-123" in kwargs["data"]


@patch('uber.open_sign.post')
def test_send_dealer_signing_invite(mock_post, monkeypatch, mock_session, mock_group):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    monkeypatch.setattr(c, 'MARKETPLACE_EMAIL', "dealers@magfest.org")
    monkeypatch.setattr(c, 'EVENT_NAME', "MAGFest")
    monkeypatch.setattr(c, 'DEALER_TERM', "Dealer")
    monkeypatch.setattr(c, 'DEALER_LOC_TERM', "Marketplace")
    monkeypatch.setattr(c, 'URL_BASE', "https://magfest.org/uber")
    monkeypatch.setattr(c, 'REDIRECT_URL_BASE', "")

    mock_response = Mock(status_code=200, content=b'{"success": true}')
    mock_post.return_value = mock_response

    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        req.group = mock_group
        req.group_leader_name = "Jane Doe"
        req.document = Mock(document_id="doc-777")
        invite_res = req.send_dealer_signing_invite()

        assert invite_res == {"success": True}
        assert not req.error_message
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert "ACTION REQUIRED: MAGFest Dealer Terms and Conditions" in kwargs["data"]


@patch('uber.open_sign.get')
def test_get_doc_signed_timestamp(mock_get, monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    mock_response = Mock(status_code=200, content=b'{"status": "completed", "completed_at": "2026-07-10T12:00:00+00:00"}')
    mock_get.return_value = mock_response

    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        req.document = Mock(document_id="doc-777")
        timestamp = req.get_doc_signed_timestamp()

        assert isinstance(timestamp, int)
        assert timestamp == int(datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC).timestamp())


@patch('uber.open_sign.get')
def test_get_download_link(mock_get, monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    mock_response = Mock(status_code=200, content=b'{"link": "https://opensign.com/download/pdf"}')
    mock_get.return_value = mock_response

    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        req.document = Mock(document_id="doc-777")
        link = req.get_download_link()

        assert link == "https://opensign.com/download/pdf"


# --- Comprehensive Branch Coverage Tests ---

def test_access_token_bytes(monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value=b"bytes-token")))
    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        assert req.access_token == "bytes-token"


def test_set_access_token_secret_name_fails(monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value=None)))
    monkeypatch.setattr(c, 'OPENSIGN_API_TOKEN', "")
    monkeypatch.setattr(c, 'AWS_OPENSIGN_SECRET_NAME', "my-secret")
    with patch('uber.tasks.redis.set_opensign_key.delay'), \
         patch('uber.config.AWSSecretFetcher.get_opensign_secret', return_value=None):
        req = OpenSignRequest(mock_session)
        assert req.error_message == "Couldn't set the OpenSign key. Check the redis task for errors."


def test_invalid_request_check_group(monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session, group=None)
        assert req.invalid_request("Action", check_group=True) is True
        assert req.error_message == "Action without a group attached to the request!"


def test_invalid_request_check_document(monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session, group=None)
        req.document = None
        assert req.invalid_request("Action", check_group=False) is True
        assert req.error_message == "Action without a document attached to the request!"


def test_check_access_token_when_missing(monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value=None)))
    monkeypatch.setattr(c, 'OPENSIGN_API_TOKEN', "")
    monkeypatch.setattr(c, 'AWS_OPENSIGN_SECRET_NAME', "")
    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        req.access_token = None
        req.check_access_token("Action")
        assert "access token is not set" in req.error_message


def test_create_dealer_signing_link_branches(monkeypatch, mock_session, mock_group):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    with patch('uber.tasks.redis.set_opensign_key.delay'):
        # 1. Invalid check_group
        req = OpenSignRequest(mock_session, group=None)
        assert req.create_dealer_signing_link() is None

        # 2. Document already signed or missing id
        req = OpenSignRequest(mock_session, group=mock_group)
        req.document = Mock(document_id=None, signed=None)
        assert req.create_dealer_signing_link() is None

        req.document = Mock(document_id="doc-123", signed=datetime.now(UTC))
        assert req.create_dealer_signing_link() is None


@patch('uber.open_sign.post')
def test_create_document_error_and_branches(mock_post, monkeypatch, mock_session, mock_group):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session, group=mock_group)
        req.document = None
        assert req.create_document("t1", "title") is None

        # HTTP error with non-JSON content
        req.error_message = ''
        req.document = Mock(document_id="doc-123")
        mock_post.return_value = Mock(status_code=500, text="Internal Server Error", content=b"Internal Server Error")
        assert req.create_document("t1", "title") is None
        assert "Internal Server Error" in req.error_message

        # HTTP 200 with JSON 'errors' list
        req.error_message = ''
        mock_post.return_value = Mock(status_code=200, content=b'{"errors": [{"message": "Invalid field"}]}')
        assert req.create_document("t1", "title") is None
        assert "Invalid field" in req.error_message

        # Nested data.objectId
        req.error_message = ''
        mock_post.return_value = Mock(status_code=200, content=b'{"data": {"objectId": "nested-id-999"}}')
        assert req.create_document("t1", "title") == "nested-id-999"


@patch('uber.open_sign.get')
def test_get_doc_signed_timestamp_branches(mock_get, monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        req.document = None
        assert req.get_doc_signed_timestamp() is None

        # details is None
        req.error_message = ''
        req.document = Mock(document_id="doc-123")
        mock_get.return_value = Mock(status_code=404, content=b'{"error": "Not found"}')
        assert req.get_doc_signed_timestamp() is None

        # status is not completed
        req.error_message = ''
        mock_get.return_value = Mock(status_code=200, content=b'{"status": "pending"}')
        assert req.get_doc_signed_timestamp() is None

        # status completed with epoch int in signed_at
        req.error_message = ''
        mock_get.return_value = Mock(status_code=200, content=b'{"status": "completed", "signed_at": 1700000000}')
        assert req.get_doc_signed_timestamp() == 1700000000

        # status signed with epoch str in updated_at
        req.error_message = ''
        mock_get.return_value = Mock(status_code=200, content=b'{"status": "signed", "updated_at": "1700000000"}')
        assert req.get_doc_signed_timestamp() == 1700000000

        # status completed with signatures created date
        req.error_message = ''
        mock_get.return_value = Mock(status_code=200, content=b'{"status": "completed", "signatures": [{"created": "2026-07-10T12:00:00Z"}]}')
        assert req.get_doc_signed_timestamp() is not None

        # status completed with invalid date string
        req.error_message = ''
        mock_get.return_value = Mock(status_code=200, content=b'{"status": "completed", "completed_at": "not-a-date"}')
        assert req.get_doc_signed_timestamp() is None


@patch('uber.open_sign.post')
def test_get_signing_link_error_and_branches(mock_post, monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        req.document = None
        assert req.get_signing_link() is None

        # HTTP error with JSON message
        req.error_message = ''
        req.document = Mock(document_id="doc-123")
        mock_post.return_value = Mock(status_code=400, content=b'{"error": "Token expired"}')
        assert req.get_signing_link() is None
        assert "Token expired" in req.error_message

        # HTTP 200 with JSON errors
        req.error_message = ''
        mock_post.return_value = Mock(status_code=200, content=b'{"errors": ["Link generation failed"]}')
        assert req.get_signing_link() is None

        # Fallback url keys
        req.error_message = ''
        mock_post.return_value = Mock(status_code=200, content=b'{"embed_url": "https://opensign.com/embed"}')
        assert req.get_signing_link() == "https://opensign.com/embed"


@patch('uber.open_sign.post')
def test_send_dealer_signing_invite_branches(mock_post, monkeypatch, mock_session, mock_group):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session, group=None)
        assert req.send_dealer_signing_invite() is None

        req = OpenSignRequest(mock_session, group=mock_group)
        req.document = Mock(document_id="doc-123")
        mock_post.return_value = Mock(status_code=400, text="Bad request", content=b"Bad request")
        assert req.send_dealer_signing_invite() is None
        assert "Bad request" in req.error_message

        req.error_message = ''
        mock_post.return_value = Mock(status_code=200, content=b'{"error": "Invite failed"}')
        assert req.send_dealer_signing_invite() is None
        assert "Invite failed" in req.error_message


@patch('uber.open_sign.get')
def test_get_download_link_branches(mock_get, monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        req.document = None
        assert req.get_download_link() is None

        req.error_message = ''
        req.document = Mock(document_id="doc-123")
        mock_get.return_value = Mock(status_code=404, text="Not found", content=b"Not found")
        assert req.get_download_link() is None
        assert "Not found" in req.error_message

        req.error_message = ''
        mock_get.return_value = Mock(status_code=200, content=b'{"errors": ["Download unavailable"]}')
        assert req.get_download_link() is None

        req.error_message = ''
        mock_get.return_value = Mock(status_code=200, content=b'{"download_url": "https://opensign.com/pdf"}')
        assert req.get_download_link() == "https://opensign.com/pdf"


@patch('uber.open_sign.get')
def test_get_document_details_branches(mock_get, monkeypatch, mock_session):
    monkeypatch.setattr(c, 'REDIS_STORE', Mock(get=Mock(return_value="token-123")))
    with patch('uber.tasks.redis.set_opensign_key.delay'):
        req = OpenSignRequest(mock_session)
        req.document = None
        assert req.get_document_details() is None

        req.error_message = ''
        req.document = Mock(document_id="doc-123")
        mock_get.return_value = Mock(status_code=500, text="Server Error", content=b"Server Error")
        assert req.get_document_details() is None
        assert "Server Error" in req.error_message

        req.error_message = ''
        mock_get.return_value = Mock(status_code=200, content=b'{"error": "Unauthorized"}')
        assert req.get_document_details() is None
        assert "Unauthorized" in req.error_message
