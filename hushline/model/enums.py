import enum
from typing import Self

from markupsafe import Markup


@enum.unique
class MessageStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    ARCHIVED = "archived"

    @classmethod
    def default(cls) -> "MessageStatus":
        return cls.PENDING

    @classmethod
    def parse_str(cls, string: str) -> Self:
        for var in cls:
            if var.value == string:
                return var
        raise ValueError(f"Invalid {cls.__name__}")

    @property
    def display_str(self) -> str:
        match self:
            case self.PENDING:
                return "Waiting"
            case self.ACCEPTED:
                return "Accepted"
            case self.DECLINED:
                return "Declined"
            case self.ARCHIVED:
                return "Archived"
            case x:
                raise Exception(f"Programming error. {self.__class__.__name__} {x!r} not handled")

    @property
    def emoji(self) -> str:
        match self:
            case self.PENDING:
                return "⏳"
            case self.ACCEPTED:
                return "✅"
            case self.DECLINED:
                return "⛔"
            case self.ARCHIVED:
                return "😴"
            case x:
                raise Exception(f"Programming error. {self.__class__.__name__} {x!r} not handled")

    @property
    def default_text(self) -> Markup:
        match self:
            case self.PENDING:
                return Markup.escape(
                    "Your message has been received. Please allow 24-72 hours for a reply. You "
                    "can check this page any time for an update."
                )
            case self.ACCEPTED:
                return Markup.escape(
                    "Thank you for contacting us. We're looking more into your case. If you left "
                    "a contact method we'll reach out to you there, too."
                )
            case self.DECLINED:
                return Markup.escape(
                    "Thank you for contacting us. Unfortunately we aren't able to move forward "
                    "with your case. Please check the Hush Line user directory to find someone "
                    "else who might be able to help."
                )
            case self.ARCHIVED:
                return Markup.escape(
                    "Your case has been archived. Contact us again if you need more help."
                )
            case x:
                raise Exception(f"Programming error. MessageStatus {x!r} not handled")


@enum.unique
class SMTPEncryption(enum.Enum):
    SSL = "SSL"
    StartTLS = "StartTLS"

    @classmethod
    def default(cls) -> "SMTPEncryption":
        return cls.StartTLS


_ACCOUNT_CATEGORY_LEGACY_LABELS = {
    "journalist_newsroom": "Journalist / Newsroom",
    "lawyer_law_firm": "Lawyer / Law Firm",
    "business_employer": "Business / Employer",
    "educator_school": "Educator / School",
    "activist_organizer": "Activist / Organizer",
    "developer_security_researcher": "Developer / Security Researcher",
}


@enum.unique
class AccountCategory(enum.Enum):
    JOURNALIST = "journalist"
    NEWSROOM = "newsroom"
    LAWYER = "lawyer"
    LAW_FIRM = "law_firm"
    BUSINESS = "business"
    NONPROFIT = "nonprofit"
    EDUCATOR = "educator"
    SCHOOL = "school"
    ACTIVIST = "activist"
    ORGANIZER = "organizer"
    DEVELOPER = "developer"
    SECURITY_RESEARCHER = "security_researcher"
    OTHER = "other"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(category.value for category in cls)

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(category.value, category.label) for category in cls]

    @classmethod
    def parse_str(cls, string: str) -> Self:
        for var in cls:
            if var.value == string:
                return var
        raise ValueError(f"Invalid {cls.__name__}")

    @classmethod
    def legacy_label(cls, string: str) -> str | None:
        return _ACCOUNT_CATEGORY_LEGACY_LABELS.get(string)

    @property
    def label(self) -> str:
        match self:
            case self.JOURNALIST:
                return "Journalist"
            case self.NEWSROOM:
                return "Newsroom"
            case self.LAWYER:
                return "Lawyer"
            case self.LAW_FIRM:
                return "Law Firm"
            case self.BUSINESS:
                return "Business"
            case self.NONPROFIT:
                return "Nonprofit"
            case self.EDUCATOR:
                return "Educator"
            case self.SCHOOL:
                return "School"
            case self.ACTIVIST:
                return "Activist"
            case self.ORGANIZER:
                return "Organizer"
            case self.DEVELOPER:
                return "Developer"
            case self.SECURITY_RESEARCHER:
                return "Security Researcher"
            case self.OTHER:
                return "Other"
            case x:
                raise Exception(f"Programming error. {self.__class__.__name__} {x!r} not handled")


@enum.unique
class StripeInvoiceStatusEnum(enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    UNCOLLECTIBLE = "uncollectible"
    VOID = "void"


@enum.unique
class StripeSubscriptionStatusEnum(enum.Enum):
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    PAUSED = "paused"


@enum.unique
class StripeEventStatusEnum(enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    ERROR = "error"
    FINISHED = "finished"


@enum.unique
class FieldType(enum.Enum):
    TEXT = "text"
    MULTILINE_TEXT = "multiline_text"
    CHOICE_SINGLE = "choice_single"
    CHOICE_MULTIPLE = "choice_multiple"

    def label(self) -> str:
        match self:
            case self.TEXT:
                return "Text"
            case self.MULTILINE_TEXT:
                return "Multiline Text"
            case self.CHOICE_SINGLE:
                return "Single Selection"
            case self.CHOICE_MULTIPLE:
                return "Multiple Selection"
            case x:
                raise Exception(f"Programming error. FieldType {x!r} not handled")
