from datetime import datetime, timezone
from extensions import db

def utcnow():
    return datetime.now(timezone.utc)

CHANNELS = ("sms", "whatsapp", "email")
MESSAGE_TYPES = (
    "payment_reminder",
    "overdue_notice",
    "high_risk_alert",
    "receipt",
    "promise_to_pay_reminder",
    "savings_maturity_notice",
    "staff_overdue_alert",
)

DELIVERY_STATUSES = ("queued", "sent", "delivered", "failed")
PROMISE_STATUSES = ("pending", "kept", "broken")

class NotificationLog(db.Model):
    """
    stores every alert sent in the system, either to customers or staff members
    """

    __tablename__ = "notification_log"
    __table_args__ = (
        db.CheckConstraint(f"channel IN {CHANNELS}", name="ck_notification_log_channel_valid"),
        db.CheckConstraint(
            f"message_type IN {MESSAGE_TYPES}", name="ck_notification_log_message_type_valid"
        ),
        db.CheckConstraint(
            f"delivery_status IN {DELIVERY_STATUSES}", name="ck_notification_log_delivery_status_valid"
        ),
        db.CheckConstraint(
            "(customer_profile_id IS NOT NULL AND recipient_user_id IS NULL) OR "
            "(customer_profile_id IS NULL AND recipient_user_id IS NOT NULL)",
            name="ck_notification_log_exactly_one_recipient",
        ),
    )
    id = db.Column(db.Integer, primary_key=True)

    customer_profile_id = db.Column(
        db.Integer, db.ForeignKey("customer_profiles.id"), nullable=True, index=True
    )
    recipient_user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=True, index=True
    )
    loan_id = db.Column(
        db.Integer, db.ForeignKey("loans.id"), nullable=True, index=True
    )

    channel = db.Column(db.String(20), nullable=False)
    message_type = db.Column(db.String(50), nullable=False)
    delivery_status = db.Column(db.String(20), nullable=False, default="queued")
    provider_reference = db.Column(db.String(255), nullable=True) #twilio message SID when applicable
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def __repr__ (self):
        return f"<NotificationLog {self.id} {self.channel}/{self.message_type} status={self.delivery_status}>"


class PromiseToPay(db.Model):
    """
    logged commitment from a customer to pay an overdue amount
    distinguishes between a customer who goes "silent" and one that promises to pay a loan
    creates another risk signal
    """

    __tablename__ = "promise_to_pay"
    __table_args__ = (
        db.CheckConstraint(
            f"status IN {PROMISE_STATUSES}", name="ck_promise_to_pay_status_valid"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)
    logged_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    promise_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self):
        return f"<PromiseToPay loan={self.loan_id} status={self.status} due={self.promised_date}>"