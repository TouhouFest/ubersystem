import asyncio
import logging
import aioboto3
from aiolimiter import AsyncLimiter

from uber.config import c

log = logging.getLogger(__name__)


class AmazonSES:
    def __init__(self, region="us-east-1"):
        self.region = region or c.AWS_REGION_EMAIL or "us-east-1"
        self.rate_limiter = AsyncLimiter(max_rate=getattr(c, 'SES_MAX_SEND_RATE', 14.0), time_period=1.0)
        self._session = aioboto3.Session(
            aws_access_key_id=c.AWS_ACCESS_KEY,
            aws_secret_access_key=c.AWS_SECRET_KEY,
            region_name=self.region
        )

    async def send_email_async(self, source, toAddresses, message, replyToAddresses=None, returnPath=None, ccAddresses=None, bccAddresses=None):
        destinations = {}
        for objName, addresses in zip(["ToAddresses", "CcAddresses", "BccAddresses"], [toAddresses, ccAddresses, bccAddresses]):
            if addresses:
                if not isinstance(addresses, str) and getattr(addresses, '__iter__', False):
                    destinations[objName] = [a for a in addresses]
                else:
                    destinations[objName] = addresses.split(', ')

        if not isinstance(replyToAddresses, str) and getattr(replyToAddresses, '__iter__', False):
            replyToEmails = [a for a in replyToAddresses]
        else:
            replyToEmails = replyToAddresses.split(', ') if replyToAddresses else []

        if not returnPath:
            returnPath = source
        message_dict = {}
        if 'bodyText' in message:
            message_dict['Text'] = {'Charset': message.get('charset') or 'UTF-8', 'Data': message['bodyText']}
        if 'bodyHtml' in message:
            message_dict['Html'] = {'Charset': message.get('charset') or 'UTF-8', 'Data': message['bodyHtml']}

        async with self.rate_limiter:
            try:
                async with self._session.client('ses', region_name=self.region) as client:
                    response = await client.send_email(
                        Source=source,
                        Destination=destinations,
                        Message={
                            'Body': message_dict,
                            'Subject': {
                                'Charset': message.get('charset') or 'UTF-8',
                                'Data': message['subject'],
                            },
                        },
                        ReplyToAddresses=replyToEmails,
                        ReturnPath=returnPath or source,
                    )
                    log.info("Sent email via aioboto3. Response: " + str(response))
                    return None
            except Exception as e:
                log.error("Error sending email via aioboto3: %s", str(e))
                return getattr(e, 'response', {}).get('Error', {}).get('Message', str(e))

    def sendEmail(self, *args, **kwargs):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            return asyncio.create_task(self.send_email_async(*args, **kwargs))
        else:
            return asyncio.run(self.send_email_async(*args, **kwargs))


email_sender = AmazonSES(c.AWS_REGION_EMAIL)
