from datetime import date, timedelta

from uber.models import WatchList, async_session
from uber.tasks import schedule


__all__ = ['deactivate_expired_watchlist_entries']


@schedule(timedelta(hours=12))
async def deactivate_expired_watchlist_entries():
    async with async_session() as session:
        expired_entries = session.query(WatchList).filter(WatchList.active == True,  # noqa: E712
                                                          WatchList.expiration != None,
                                                          WatchList.expiration <= date.today())

        expired_count = expired_entries.count()

        for entry in expired_entries:
            entry.active = False
            session.add(entry)

        await session.commit()
        return f"Deactivated {expired_count} expired watchlist entries."