from uber.tasks import task
from uber.models import async_session
from sqlalchemy import text


@task
async def ping(response):
    async with async_session() as session:
        await session.execute(text('SELECT 1'))
    return response
