from abc import abstractmethod
from uber.config import c


class EmailSender:
    @abstractmethod
    def sendEmail(
        self, source: str, toAddresses: str | list[str],
        message: dict[str, str],
        replyToAddresses: str | list[str] | None = None,
        returnPath: str | None = None,
        ccAddresses: str | list[str] | None = None,
        bccAddresses: str | list[str] | None = None
    ) -> str | Exception:
        pass


class EmailSenderRegistry:
    def __init__(self) -> None:
        self.__email_senders: dict[str, type[EmailSender]] = {}

    @property
    def email_sender(self) -> EmailSender:
        return self.__email_sender

    def register(self, name: str, email_sender: type[EmailSender]) -> None:
        self.__email_senders[name] = email_sender

    def initialize(self) -> None:
        try:
            self.__email_sender = self.__email_senders[c.EMAIL_SENDER]()
        except KeyError:
            raise KeyError(
                f"no email senders named '{c.EMAIL_SENDER}' registered"
            )


registry = EmailSenderRegistry()
