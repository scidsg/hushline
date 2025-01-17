import enum

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

    @property
    def display_str(self) -> str:
        match self:
            case self.PENDING:
                return "⏳ Waiting for Response"
            case self.ACCEPTED:
                return "✅ Accepted"
            case self.DECLINED:
                return "⛔ Declined"
            case self.ARCHIVED:
                return "😴 Archived"
            case x:
                raise Exception(f"Programming error. MessageStatus {x!r} not handled")

    @property
    def default_text(self) -> Markup:
        match self:
            case self.PENDING:
                return Markup.escape(
                    "Your message has been received. Please allow 24-72 hours for a reply. You "
                    "can check this page any time for an update. Messages expire after 30 days."
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
                return "Single Choice"
            case self.CHOICE_MULTIPLE:
                return "Multiple Choice"
            case x:
                raise Exception(f"Programming error. FieldType {x!r} not handled")

    @classmethod
    def default(cls) -> "FieldType":
        return cls.TEXT
