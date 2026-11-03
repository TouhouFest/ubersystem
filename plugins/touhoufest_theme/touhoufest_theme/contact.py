import json
import logging
from typing import Any

import cherrypy

from uber.amazon_ses import email_sender
from uber.config import c

log = logging.getLogger(__name__)

ALLOWED_ORIGINS: tuple[str, ...] = (
    'https://touhoufest.org',
    'https://www.touhoufest.org',
    'https://staging.touhoufest.org',
    'http://localhost:1111',
    'http://127.0.0.1:1111',
)

CATEGORY_LABELS: dict[str, str] = {
    'general': 'General Inquiry',
    'badges': 'Ticketing / Badges',
    'artists': 'Artist Alley / Vendors',
    'panels': 'Panels & Programming',
    'volunteering': 'Volunteering & Staff',
    'press': 'Press & Media',
    'accessibility': 'Accessibility',
    'other': 'Other',
}

CONTACT_RECIPIENT = 'touhoufest@gmail.com'


def _sanitize_single_line(value: str, max_chars: int) -> str:
    cleaned = ''.join(' ' if ch in ('\r', '\n', '\0') else ch for ch in value)
    return cleaned[:max_chars].strip()


def _resolve_origin() -> str:
    headers = cherrypy.request.headers
    origin = headers.get('Origin', '')
    for allowed in ALLOWED_ORIGINS:
        if origin.lower() == allowed.lower():
            return allowed

    referer = headers.get('Referer', '')
    for allowed in ALLOWED_ORIGINS:
        if referer.startswith(allowed):
            return allowed

    return ALLOWED_ORIGINS[0]


def _set_cors_headers(origin: str) -> None:
    resp_headers = cherrypy.response.headers
    resp_headers['Access-Control-Allow-Origin'] = origin
    resp_headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    resp_headers['Access-Control-Allow-Headers'] = 'Content-Type, Accept'
    resp_headers['Vary'] = 'Origin'


def _wants_json() -> bool:
    accept = cherrypy.request.headers.get('Accept', '')
    return 'application/json' in accept


def _json_response(status: int, payload: dict[str, Any]) -> bytes:
    cherrypy.response.status = status
    cherrypy.response.headers['Content-Type'] = 'application/json'
    return json.dumps(payload).encode('utf-8')


def _respond_success(origin: str, is_json: bool) -> bytes:
    if is_json:
        return _json_response(200, {'ok': True})
    raise cherrypy.HTTPRedirect(f'{origin}/about/contact/#contact-submitted', 303)


def _respond_error(origin: str, is_json: bool, status: int, message: str) -> bytes:
    if is_json:
        return _json_response(status, {'ok': False, 'error': message})
    raise cherrypy.HTTPRedirect(f'{origin}/about/contact/#contact-error', 303)


def _validate_email(email: str) -> str | None:
    if not email or len(email) > 254:
        return 'A valid email address is required.'
    if any(ch in email for ch in ('\r', '\n', '\0')):
        return 'Invalid characters in email address.'
    if '@' not in email:
        return 'A valid email address is required.'
    local, _, domain = email.partition('@')
    if not local or '.' not in domain or domain.startswith('.') or domain.endswith('.'):
        return 'A valid email address is required.'
    return None


def _extract_payload(params: dict[str, Any]) -> dict[str, str]:
    content_type = cherrypy.request.headers.get('Content-Type', '')
    raw_data: dict[str, Any] = dict(params)
    if 'application/json' in content_type and cherrypy.request.body is not None:
        raw_bytes = cherrypy.request.body.read()
        if raw_bytes:
            parsed = json.loads(raw_bytes.decode('utf-8'))
            if isinstance(parsed, dict):
                raw_data.update(parsed)

    return {
        key: str(val) if val is not None else ''
        for key, val in raw_data.items()
    }


@cherrypy.expose
@cherrypy.config(**{'tools.sessions.on': False})
def contact(self: Any, **params: Any) -> bytes:
    origin = _resolve_origin()
    _set_cors_headers(origin)
    method = cherrypy.request.method.upper()

    if method == 'OPTIONS':
        cherrypy.response.status = 204
        return b''

    is_json = _wants_json()
    if method != 'POST':
        return _respond_error(origin, is_json, 405, 'Method Not Allowed')

    try:
        data = _extract_payload(params)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        return _respond_error(origin, is_json, 400, 'Invalid form payload.')

    if data.get('_gotcha', '').strip():
        return _respond_success(origin, is_json)

    email = data.get('email', '').strip()
    if email_err := _validate_email(email):
        return _respond_error(origin, is_json, 400, email_err)

    name = _sanitize_single_line(data.get('name', ''), 200)
    if not name:
        return _respond_error(origin, is_json, 400, 'Name is required.')

    raw_category = _sanitize_single_line(data.get('category', ''), 100)
    if not raw_category:
        return _respond_error(origin, is_json, 400, 'Please select a reason for contacting us.')

    message_body = data.get('message', '').strip()
    if len(message_body) > 10_000:
        return _respond_error(origin, is_json, 400, 'Message exceeds maximum length.')

    category_label = CATEGORY_LABELS.get(raw_category, raw_category)
    title = _sanitize_single_line(data.get('subject', ''), 200)
    if title:
        subject_line = f'[TouhouFest Contact] [{category_label}] {title} ({name})'
    else:
        subject_line = f'[TouhouFest Contact] [{category_label}] Inquiry from {name}'

    lines = [
        'New TouhouFest Contact Form Submission',
        '======================================',
        f'Name: {name}',
        f'Email: {email}',
        f'Category: {category_label}',
    ]
    if pronouns := _sanitize_single_line(data.get('pronouns', ''), 100):
        lines.append(f'Pronoun(s): {pronouns}')
    if organization := _sanitize_single_line(data.get('organization', ''), 200):
        lines.append(f'Company/Organization: {organization}')
    if title:
        lines.append(f'Title: {title}')
    if phone := _sanitize_single_line(data.get('phone', ''), 50):
        lines.append(f'Phone: {phone}')
    if website := _sanitize_single_line(data.get('website', ''), 500):
        lines.append(f'Website: {website}')

    lines.extend([
        '',
        'Message:',
        '--------------------------------------',
        message_body or '(No message body provided)',
    ])

    if c.SEND_EMAILS:
        err = email_sender.sendEmail(
            source=c.CONTACT_EMAIL,
            toAddresses=[CONTACT_RECIPIENT],
            message={
                'charset': 'UTF-8',
                'subject': subject_line,
                'bodyText': '\n'.join(lines),
            },
            replyToAddresses=[email],
        )
        if err is not None:
            log.error('Failed to send contact form email via SES: %s', err)
            return _respond_error(
                origin,
                is_json,
                502,
                'Failed to send email. Please try again later.',
            )

    return _respond_success(origin, is_json)
