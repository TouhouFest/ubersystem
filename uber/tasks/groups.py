import asyncio
import pytz
import logging

from datetime import datetime, timedelta
from sqlalchemy.orm.exc import NoResultFound

from uber.email import EmailService
from uber.config import c
from uber.decorators import render
from uber.models import Group, GuestGroup, GuestMerch, async_session
from uber.tasks import schedule, crontab
from uber.utils import SignNowRequest, localized_now

log = logging.getLogger(__name__)

__all__ = ['check_document_signed', 'convert_declined_groups', 'rock_island_updates']


@schedule(crontab(minute=0, hour='*/6'))
async def check_document_signed():
    from uber.models import SignedDocument
    if not c.SIGNNOW_DEALER_TEMPLATE_ID:
        return
    
    signnow_limiter = asyncio.Semaphore(10)

    async with async_session() as session:
        unsigned_docs = session.query(SignedDocument).filter_by(model="Group").all()
        targets = []
        for document in unsigned_docs:
            if not document.signed:
                try:
                    group = session.group(document.fk_id)
                    targets.append((document, group))
                except NoResultFound:
                    log.debug(f"Signed document {document.id} is dangling, group {document.fk_id} not found.")

        async def check_single_doc(document, group):
            async with signnow_limiter:
                signnow_request = SignNowRequest(session=session, group=group)
                signed = await asyncio.to_thread(signnow_request.get_doc_signed_timestamp)
                return document, signnow_request, signed

        tasks = [check_single_doc(doc, grp) for doc, grp in targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, Exception) or not res:
                continue
            document, signnow_request, signed = res
            if signed:
                signnow_request.document.signed = datetime.fromtimestamp(int(signed))
                signnow_link = ''
                signnow_request.document.link = signnow_link
                session.add(signnow_request.document)
        await session.commit()


@schedule(timedelta(hours=12))
async def convert_declined_groups():
    from uber.site_sections.dealer_admin import decline_and_convert_dealer_group

    async with async_session() as session:
        declined_groups = session.query(Group).filter(Group.status == c.DECLINED,
                                                      Group.convert_badges == True,
                                                      Group.badges_purchased > 0)
        for group in declined_groups:
            name = group.name
            result = await asyncio.to_thread(decline_and_convert_dealer_group, session, group, delete_group=c.DELETE_DECLINED_GROUPS)
            log.debug(f"{name} converted: {result}")


@schedule(crontab(minute=0, hour=0))
async def rock_island_updates():
    async with async_session() as session:
        updated_ri_inventories = session.query(GuestGroup).join(
            GuestMerch, GuestGroup.merch).filter(
                GuestMerch.inventory_updated > datetime.now(pytz.UTC) - timedelta(hours=24))
        if updated_ri_inventories.count():
            EmailService.queue_email(session, 'rock_island_updates_admin', to=c.ROCK_ISLAND_EMAIL,
                                     subject=f'{c.EVENT_NAME} Rock Island Inventory Updates for {localized_now().strftime("%Y-%m-%d")}',
                                     data={'updated_ri_inventories': updated_ri_inventories}, replace_unsent=True)
