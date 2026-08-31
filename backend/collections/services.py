from typing import Optional

from extensions import db
from foundations.auth import AuthError, get_user_institution_id, verify_institution_access
from foundations.audit import log_action
from origination.services import get_customer_profile
from underwriting.services import get_loan

from collections.models import NotificationLog, PromiseToPay, CHANNELS, MESSAGE_TYPES, utcnow
from collections.notifications import dispatch, NotificationDispatchError

def _verify_staff_institution_access(user_id:int) -> None:
    #institution check, makes sure staff has access to their own institution
    institution_id = get_user_institution_id(user_id)
    if not institution_id:
        raise AuthError("No such staff user, ot user has no institution.", 400)
    verify_institution_access(user_id, institution_id)

#------- sending a notification ---------

def send_notification(
    actor_id: int,
    channel: str,
    message_type: str,
    body: str,
    customer_profile_id: Optional[int] = None,
    recipient_user_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    subject: Optional[str] = None,
    recipient_contact: Optional[str] = None,
) -> NotificationLog:

    if (customer_profile_id is None) == (recipient_user_id is None):
        raise AuthError(
            "Exactly one of customer_profile_id or recipient_user_id must be provided.",
            400
        )

    if channel not in CHANNELS:
        raise AuthError(
            f"Invalid channel '{channel}'. Must be one of {CHANNELS}.",
            400
        )

    if message_type not in MESSAGE_TYPES:
        raise AuthError(
            f"Invalid message type '{message_type}'. Must be one of {MESSAGE_TYPES}.",
            400
        )

    if customer_profile_id is not None:
        if channel == "email":
            raise AuthError("Cannot send email to customer", 400)
        profile = get_customer_profile(customer_profile_id) #institution check enforced
        contact = profile.phone_number
        if not contact:
            raise AuthError(
                "Customer profile has no phone number.",
                400
            )
        else:
            _verify_staff_institution_access(recipient_user_id)
            if not recipient_contact:
                raise AuthError(
                    "recipient_contact is required for staff-directed notifications "
                    "(no Foundation resolver function exists yet — see [OPEN] note).",
                    400,
                )
            contact = recipient_contact

    if loan_id is not None:
        get_loan(loan_id)

    entry = NotificationLog(
        customer_profile_id=customer_profile_id,
        recipient_user_id=recipient_user_id,
        loan_id=loan_id,
        channel=channel,
        message_type=message_type,
        delivery_status="queued",
    )
    db.session.add(entry)
    db.session.commit()

    try:
        provider_reference = dispatch(channel, contact, body, subject=subject)
        entry.delivery_status = "sent"
        entry.provider_reference = provider_reference
        entry.sent_at = utcnow()
    except NotificationDispatchError:
        entry.delivery_status = "failed"

        db.session.commit()
        log_action(
            actor_id=actor_id,
            entity_type="NotificationLog",
            entity_id=entry.id,
            action="update",
            before={"delivery_status": "queued"},
            after={"delivery_status": "failed"},
        )
        raise

    db.session.commit()
    log_action(
        actor_id=actor_id,
        entity_type="NotificationLog",
        entity_id=entry.id,
        action="create",
        before=None,
        after={"channel": channel, "message_type": message_type, "delivery_status": "sent"},
    )

    return entry


#-------- Aging / risk classification --------

def classify_aging_bucket(
    days_overdue: int
) -> str:
    if days_overdue <= 0:
        return "current"
    elif days_overdue <= 30:
        return "0-30"
    elif days_overdue <= 60:
        return "31-60"
    elif days_overdue <= 90:
        return "61-90"
    else:
        return "90+"

def is_high_risk(
    aging_bucket: str,
    broken_promise_count: int
) -> bool:
    return aging_bucket in ("61-90", "90+") or broken_promise_count >= 2