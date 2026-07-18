from datetime import timedelta
from uber.tasks import crontab, schedule_to_cron, saq_app


def test_schedule_to_cron_conversion():
    # Test timedelta conversions
    assert schedule_to_cron(timedelta(minutes=5)) == "*/5 * * * *"
    assert schedule_to_cron(timedelta(hours=1)) == "0 */1 * * *"
    assert schedule_to_cron(timedelta(days=1)) == "0 0 */1 * *"

    # Test crontab conversions
    cron1 = crontab(hour=6, minute=0, day_of_week=1)
    assert schedule_to_cron(cron1) == "0 6 * * 1"

    cron2 = crontab(minute=0, hour='*/6')
    assert schedule_to_cron(cron2) == "0 */6 * * *"


def test_saq_app_task_registration():
    @saq_app.task
    def sample_sync_task(arg1, key=None):
        return f"{arg1}:{key}"

    @saq_app.task
    async def sample_async_task(arg1, key=None):
        return f"async:{arg1}:{key}"

    assert "sample_sync_task" in saq_app.registered_functions
    assert "sample_async_task" in saq_app.registered_functions
    assert hasattr(sample_sync_task, "delay")
    assert hasattr(sample_async_task, "delay")


def test_saq_app_schedule_registration():
    @saq_app.schedule(timedelta(minutes=15))
    def scheduled_sample():
        pass

    matching = [job for job in saq_app.cron_jobs if job["cron"] == "*/15 * * * *"]
    assert len(matching) >= 1


def test_async_rate_limiter():
    import asyncio
    from aiolimiter import AsyncLimiter

    limiter = AsyncLimiter(max_rate=100.0, time_period=1.0)
    counter = 0

    async def run_test():
        nonlocal counter
        async def work():
            nonlocal counter
            async with limiter:
                counter += 1
                await asyncio.sleep(0.001)

        await asyncio.gather(*[work() for _ in range(10)])

    asyncio.run(run_test())
    assert counter == 10
