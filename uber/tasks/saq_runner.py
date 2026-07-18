import asyncio
import logging
import sys

from uber.tasks.saq_app import saq_app

# Import all task modules so all task definitions and schedules are registered with saq_app
import uber.tasks.attractions  # noqa: F401
import uber.tasks.email  # noqa: F401
import uber.tasks.groups  # noqa: F401
import uber.tasks.health  # noqa: F401
import uber.tasks.mivs  # noqa: F401
import uber.tasks.panels  # noqa: F401
import uber.tasks.redis  # noqa: F401
import uber.tasks.registration  # noqa: F401
import uber.tasks.security  # noqa: F401
import uber.tasks.sms  # noqa: F401

log = logging.getLogger(__name__)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    log.info("Starting Ubersystem SAQ Async Task Worker and Cron Scheduler...")
    worker = saq_app.get_worker(concurrency=20)
    await worker.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("SAQ Async Worker stopped.")
