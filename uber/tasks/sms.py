import asyncio
import logging
from time import sleep

from aiolimiter import AsyncLimiter
from twilio.base.exceptions import TwilioRestException
from twilio.http.async_http_client import AsyncHttpClient
from twilio.rest import Client as TwilioRestClient

from uber.config import c
from uber.tasks import task
from uber.utils import normalize_phone
from uber.custom_tags import readable_join

log = logging.getLogger(__name__)

__all__ = ['get_twilio_client', 'get_async_twilio_client', 'send_sms', 'send_sms_with_client', 'send_sms_async', 'send_sms_with_client_async']

twilio_rate_limiter = AsyncLimiter(max_rate=10.0, time_period=1.0)


def get_twilio_client(twilio_sid, twilio_token):
    if c.SEND_SMS:
        try:
            if twilio_sid and twilio_token:
                return TwilioRestClient(twilio_sid, twilio_token)
            else:
                log.info('Twilio: could not create twilio client. Missing twilio {}.'.format(
                    readable_join(['' if twilio_sid else 'SID', '' if twilio_token else 'TOKEN'])))
        except Exception:
            log.error('Twilio: could not create twilio client', exc_info=True)
    return None


def get_async_twilio_client(twilio_sid, twilio_token):
    if c.SEND_SMS:
        try:
            if twilio_sid and twilio_token:
                http_client = AsyncHttpClient(logger=log, is_async=True)
                return TwilioRestClient(twilio_sid, twilio_token, http_client=http_client)
        except Exception:
            log.error('Twilio: could not create async twilio client', exc_info=True)
    return None


@task
async def send_sms(twilio_sid, twilio_token, to, body, from_):
    client = get_async_twilio_client(twilio_sid, twilio_token) or get_twilio_client(twilio_sid, twilio_token)
    return await send_sms_with_client_async(client, to, body, from_)


async def send_sms_async(twilio_sid, twilio_token, to, body, from_):
    client = get_async_twilio_client(twilio_sid, twilio_token) or get_twilio_client(twilio_sid, twilio_token)
    return await send_sms_with_client_async(client, to, body, from_)


async def send_sms_with_client_async(twilio_client, to, body, from_):
    message = None
    sid = 'Unable to send SMS'
    if not twilio_client:
        log.error('No twilio client configured')
        return sid

    to = normalize_phone(to)
    if c.DEV_BOX and to not in c.TESTING_PHONE_NUMBERS:
        log.info('We are in DEV BOX mode, so we are not sending {!r} to {!r}', body, to)
        return 'DEV_BOX_SKIPPED'

    async with twilio_rate_limiter:
        try:
            if hasattr(twilio_client.messages, 'create_async'):
                message = await twilio_client.messages.create_async(to=to, body=body, from_=normalize_phone(from_))
            else:
                message = await asyncio.to_thread(twilio_client.messages.create, to=to, body=body, from_=normalize_phone(from_))
        except TwilioRestException as e:
            if e.code == 21211:  # https://www.twilio.com/docs/api/errors/21211
                log.error('Invalid cellphone number %s', to, exc_info=True)
            else:
                log.error('Twilio: exception while sending SMS to %s: %s', to, str(e), exc_info=True)
            return str(e)
        except Exception as e:
            log.error('Twilio: unexpected error sending SMS to %s: %s', to, str(e), exc_info=True)
            return str(e)

    if message:
        sid = message.sid if not getattr(message, 'error_code', None) else getattr(message, 'error_text', 'Twilio error')
    return sid


def send_sms_with_client(twilio_client, to, body, from_):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        return asyncio.create_task(send_sms_with_client_async(twilio_client, to, body, from_))
    else:
        return asyncio.run(send_sms_with_client_async(twilio_client, to, body, from_))
