import logging
from datetime import timedelta

from uber.config import _config as config_dict
from uber.models import Session, async_session
from uber.tasks.saq_app import saq_app, schedule_to_cron

log = logging.getLogger(__name__)

__all__ = ['task', 'schedule', 'on_startup', 'crontab', 'saq_app', 'celery', 'async_session']


class CrontabSchedule:
    def __init__(self, minute="*", hour="*", day_of_month="*", month_of_year="*", day_of_week="*"):
        self.minute = minute
        self.hour = hour
        self.day_of_month = day_of_month
        self.month_of_year = month_of_year
        self.day_of_week = day_of_week

    def __str__(self):
        return f"{self.minute} {self.hour} {self.day_of_month} {self.month_of_year} {self.day_of_week}"


def crontab(minute="*", hour="*", day_of_month="*", month_of_year="*", day_of_week="*"):
    return CrontabSchedule(minute=minute, hour=hour, day_of_month=day_of_month,
                           month_of_year=month_of_year, day_of_week=day_of_week)


task = saq_app.task
schedule = saq_app.schedule


def on_startup(fn, *args, **kwargs):
    registered = saq_app.task(fn)
    return registered


class CeleryCompatShim:
    """Backward compatibility shim mapping legacy Celery decorator calls to SAQ."""
    def __init__(self, app):
        self.app = app
        self.task = app.task
        self.schedule = app.schedule
        self.on_startup = on_startup


celery = CeleryCompatShim(saq_app)


from uber.tasks import attractions  # noqa: F401, E402
from uber.tasks import email  # noqa: F401, E402
from uber.tasks import groups  # noqa: F401, E402
from uber.tasks import health  # noqa: F401, E402
from uber.tasks import mivs  # noqa: F401, E402
from uber.tasks import panels  # noqa: F401, E402
from uber.tasks import redis  # noqa: F401, E402
from uber.tasks import registration  # noqa: F401, E402
from uber.tasks import security  # noqa: F401, E402
from uber.tasks import sms  # noqa: F401, E402
