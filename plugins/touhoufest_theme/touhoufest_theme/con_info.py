import json
from typing import Any

import cherrypy
from uber.config import c


def _set_cors_headers() -> None:
    resp_headers = cherrypy.response.headers
    resp_headers["Access-Control-Allow-Origin"] = "*"
    resp_headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp_headers["Access-Control-Allow-Headers"] = "Content-Type, Accept"


def _format_date(val: Any) -> str | None:
    if val is None or val == "":
        return None
    if hasattr(val, "isoformat"):
        return str(val.isoformat())
    return str(val)


def _json_response(status: int, payload: dict[str, Any]) -> bytes:
    cherrypy.response.status = status
    cherrypy.response.headers["Content-Type"] = "application/json"
    return json.dumps(payload).encode("utf-8")


def _build_con_info() -> dict[str, Any]:
    single_day_prices = getattr(c, "SINGLE_DAY_PRICES", None)
    if not isinstance(single_day_prices, dict):
        badge_prices = getattr(c, "BADGE_PRICES", {})
        single_day_prices = (
            badge_prices.get("single_day", {}) if isinstance(badge_prices, dict) else {}
        )

    vendor_prices = getattr(c, "VENDOR_PRICES", {}) or {}
    discounted_badges = getattr(c, "DEALER_DISCOUNTED_BADGES", {}) or {}
    vendor_types = [
        {
            "key": key,
            "label": label,
            "price": vendor_prices.get(key),
            "discounted_badges": (
                discounted_badges.get(key, 0)
                if isinstance(discounted_badges, dict)
                else int(discounted_badges or 0)
            ),
        }
        for key, label in getattr(c, "VENDOR_TYPE_OPTS", ())
    ]

    return {
        "event_name": c.EVENT_NAME,
        "year": getattr(c, "YEAR", None) or getattr(c, "EVENT_YEAR", ""),
        "organization_name": c.ORGANIZATION_NAME,
        "event_timezone": str(c.EVENT_TIMEZONE),
        "event_venue": c.EVENT_VENUE,
        "event_venue_address": (
            getattr(c, "EVENT_VENUE_ADDRESS", "")
            or getattr(c, "EVENT_VALUE_ADDRESS", "")
        ),
        "urls": {
            "url_root": c.URL_ROOT,
            "alt_schedule_url": c.ALT_SCHEDULE_URL,
            "code_of_conduct_url": c.CODE_OF_CONDUCT_URL,
            "privacy_policy_url": c.PRIVACY_POLICY_URL,
            "contact_url": c.CONTACT_URL,
            "prereg_faq_url": c.PREREG_FAQ_URL,
            "volunteer_perks_url": c.VOLUNTEER_PERKS_URL,
            "exhibitor_info_url": c.EXHIBITOR_INFO_URL,
        },
        "dates": {
            "epoch": _format_date(c.EPOCH),
            "eschaton": _format_date(c.ESCHATON),
            "prereg_open": _format_date(c.PREREG_OPEN),
            "refund_cutoff": _format_date(c.REFUND_CUTOFF),
            "printed_badge_deadline": _format_date(c.PRINTED_BADGE_DEADLINE),
            "dealer_reg_start": _format_date(c.DEALER_REG_START),
            "dealer_reg_deadline": _format_date(c.DEALER_REG_DEADLINE),
            "dealer_reg_shutdown": _format_date(c.DEALER_REG_SHUTDOWN),
            "panels_start": _format_date(getattr(c, "PANELS_START", None)),
            "panels_deadline": _format_date(getattr(c, "PANELS_DEADLINE", None)),
        },
        "status": {
            "at_the_con": bool(c.AT_THE_CON),
            "post_con": bool(c.POST_CON),
            "hide_schedule": bool(c.HIDE_SCHEDULE),
            "before_prereg_takedown": bool(c.BEFORE_PREREG_TAKEDOWN),
            "dealer_reg_open": bool(
                c.DEALER_REG_START and c.DEALER_REG_PUBLIC and c.DEALER_REG_OPEN
            ),
            "panels_open": bool(getattr(c, "BEFORE_PANELS_DEADLINE", False)),
        },
        "badges": {
            "one_days_enabled": bool(c.ONE_DAYS_ENABLED),
            "initial_attendee": c.INITIAL_ATTENDEE,
            "attendee_price": c.BADGE_PRICE,
            "saturday_price": single_day_prices.get("Saturday"),
            "sunday_price": single_day_prices.get("Sunday"),
            "dealer_badge_price": c.DEALER_BADGE_PRICE,
            "sold_out_badge_types": list(c.SOLD_OUT_BADGE_TYPES),
        },
        "vendor_types": vendor_types,
    }


@cherrypy.expose
@cherrypy.config(**{"tools.sessions.on": False})
def con_info(self: Any, **params: Any) -> bytes:
    _set_cors_headers()
    method = cherrypy.request.method.upper()

    if method == "OPTIONS":
        cherrypy.response.status = 204
        return b""

    if method != "GET":
        return _json_response(405, {"error": "Method Not Allowed"})

    return _json_response(200, _build_con_info())
