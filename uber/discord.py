import aiohttp
import asyncio
import logging
import threading
from discord import Webhook
from uber.config import c

log = logging.getLogger(__name__)


_loop = None
_webhook = None
_url = getattr(c, 'DISCORD_BADGE_SOLD_WEBHOOK_URL', '')
if _url:
    _init_event = threading.Event()
    async def _init_webhook():
        global _webhook
        session = aiohttp.ClientSession()
        _webhook = Webhook.from_url(_url, session=session)

    def _start_loop():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _loop.run_until_complete(_init_webhook())
        _init_event.set()
        _loop.run_forever()

    _thread = threading.Thread(target=_start_loop, daemon=True)
    _thread.start()
    _init_event.wait()

async def _send(content: str):
    try:
        await _webhook.send(content=content)
    except Exception as e:
        log.warning(f"Failed to send Discord webhook to {_url}: {e}")


def send_discord_webhook(content: str):
    if not _webhook:
        log.warning("Could not send Discord notification without configured Discord webhook")
        return
    asyncio.run_coroutine_threadsafe(_send(content), _loop)


def notify_badge_sold(attendee_or_group=None):
    """
    Sends a privacy-safe, single-line Discord text notification when a badge is sold.
    Omits attendee/group names, badge types, and payment amounts for privacy.
    """
    event_name = getattr(c, 'EVENT_NAME_AND_YEAR', '') or getattr(c, 'EVENT_NAME', 'Ubersystem')
    content = f"<a:JoonMoney:1037326830883061760> **Badge Sold for {event_name}!**"

    if c.BADGES_SOLD:
        content += f", Total sold: **{c.BADGES_SOLD}**"
    if c.ATTENDEE_BADGE_STOCK:
        content += f", Remaining: **{c.REMAINING_BADGES}**"

    send_discord_webhook(content)


def notify_near_cap(badges_left: int):
    """
    Sends a single-line Discord text alert when badge stock reaches a low threshold.
    """
    event_name = getattr(c, 'EVENT_NAME_AND_YEAR', '') or getattr(c, 'EVENT_NAME', 'Ubersystem')
    content = f"<a:KasenPanic:1037326830883061760> **Low Badge Stock Alert - {event_name}:** Only **{badges_left}** badges remaining!"
    send_discord_webhook(content)


def notify_badge_refunded(attendee_or_group=None):
    """
    Sends a privacy-safe, single-line Discord text notification when a badge is refunded.
    Omits attendee/group names, badge types, and refund amounts for privacy.
    """
    event_name = getattr(c, 'EVENT_NAME_AND_YEAR', '') or getattr(c, 'EVENT_NAME', 'Ubersystem')
    content = f"<:NotLikeShion:939625922296938546> **Badge Refunded for {event_name}!**"

    if getattr(c, 'BADGES_SOLD', None):
        content += f", Total sold: **{c.BADGES_SOLD}**"
    if getattr(c, 'ATTENDEE_BADGE_STOCK', None) and getattr(c, 'REMAINING_BADGES', None):
        content += f", Remaining: **{c.REMAINING_BADGES}**"

    send_discord_webhook(content)
