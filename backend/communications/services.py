from typing import Optional

from extensions import db
from foundations.auth import AuthError, get_user_institution_id, verify_institution_access
from foundations.audit import log_action
from origination.services import get_customer_profile
from underwriting.services import get_loan, list_loans_for_institution

from collections.models import NotificationLog, PromiseToPay, CHANNELS, MESSAGE_TYPES, utcnow
from collections.notifications import dispatch, NotificationDispatchError

def _verify_staff_institution_access(user_id:int) -> None:
    #institution check, makes sure staff has access to their own institution
    institution_id = get_user_institution_id(user_id)
    if not institution_id:
        raise AuthError("No such staff user, ot user has no institution.", 400)
    verify_institution_access(user_id, institution_id)

#------- notification aggregates --------

def get_notification_summary(
    actor_id: int,
    since=None
) -> dict:
    """
    for analytics/ reporting module
    Institution scoping is done by first calling
    underwriting.services.list_loans_for_institution() to get this
    institution's loan_ids, then filtering NotificationLog against those
    plain integers — NOT by importing or joining against Underwriting's
    Loan model directly, which would violate the one rule.
    """

    loan_ids = [loan.id for loan in list_loans_for_institution(actor_id)]
    if not loan_ids:
        return {"total": 0, "by_channel": {}, "by_message_type": {}, "by_delivery_status": {}}
 
    query = NotificationLog.query.filter(NotificationLog.loan_id.in_(loan_ids))
    if since is not None:
        query = query.filter(NotificationLog.sent_at >= since)
    logs = query.all()
 
    summary = {"total": len(logs), "by_channel": {}, "by_message_type": {}, "by_delivery_status": {}}
    for entry in logs:
        summary["by_channel"][entry.channel] = summary["by_channel"].get(entry.channel, 0) + 1
        summary["by_message_type"][entry.message_type] = (
            summary["by_message_type"].get(entry.message_type, 0) + 1
        )
        summary["by_delivery_status"][entry.delivery_status] = (
            summary["by_delivery_status"].get(entry.delivery_status, 0) + 1
        )
 
    return summary

def get_broken_promise_counts(actor_id: int) -> dict:
    """
    Maps loan_id -> count of broken promises, for this institution's
    loans. Same scoping approach as get_notification_summary() — goes
    through list_loans_for_institution() rather than a direct join.
    """
    loan_ids = [loan.id for loan in list_loans_for_institution(actor_id)]
    if not loan_ids:
        return {}
 
    rows = (
        db.session.query(PromiseToPay.loan_id, db.func.count(PromiseToPay.id))
        .filter(PromiseToPay.loan_id.in_(loan_ids), PromiseToPay.status == "broken")
        .group_by(PromiseToPay.loan_id)
        .all()
    )
    return {loan_id: count for loan_id, count in rows}

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

#------ Servicing dependent(stubs) -------

def run_overdue_detection() -> None:
    """
    is a stub for now
    calls servicing.services.get_overdue_schedules(), classify each via 
    classify_aging_bucket()
    calls send_notification() for anything crossing a new bucket threshold
    """
    raise NotImplementedError(
        "Servicing module not yet built (Phase 3). See docstring for the intended flow "
        "once servicing.services.get_overdue_schedules() exists."
    )

def dispatch_receipt(
    loan_id: int,
    actor_id: Optional[int] = None
) -> NotificationLog:
    """
    called by servicing to dispatch receipt
    takes a loan_id and sends a receipt to that loan's customer
    """
    loan = get_loan(loan_id) #institution check enforced internally
    return send_notification(
        actor_id=actor_id if actor_id is not None else loan.customer_profile_id,
        channel="sms",
        message_type="receipt",
        body=f"Payment received for loan #{loan.id}. Thank you.",
        customer_profile_id=loan.customer_profile_id,
        loan_id=loan.id,
    )



# ------ Promise-to-pay lifecycle ---------

def log_promise_to_pay(
    loan_id:int,
    promised_date,
    actor_id:int
) -> PromiseToPay:
    loan = get_loan(loan_id) #institution check enforced internally

    promise = PromiseToPay(
        loan_id=loan.id,
        logged_by_user_id=actor_id,
        promised_date=promised_date,
        status="pending",
    )
    db.session.add(promise)
    db.session.commit()

    log_action(
        actor_id=actor_id,
        entity_type="PromiseToPay",
        entity_id=promise.id,
        action="create",
        before=None,
        after={"loan_id": loan.id, "promised_date": str(promised_date)},
        lending_institution_id=loan.lending_institution_id,
    )

    return promise

def _update_promise_status(
    promise_id: int,
    new_status:str,
    actor_id: int
) -> PromiseToPay:
    promise = db.session.get(PromiseToPay, promise_id)
    if promise is None:
        raise AuthError("No such promise.", 404)

    loan = get_loan(promise.loan_id) #institution check enforced internally

    before = {"status": promise.status}
    promise.status = new_status

    db.session.commit()

    log_action(
        actor_id=actor_id,
        entity_type="PromiseToPay",
        entity_id=promise.id,
        action="update",
        before=before,
        after={"status": new_status},
        lending_institution_id=loan.lending_institution_id,
    )

    return promise


def mark_promise_kept(
    promise_id: int,
    actor_id: int
) -> PromiseToPay:
    return _update_promise_status(promise_id,"kept",actor_id)


def mark_promise_broken(
    promise_id:int,
    actor_id:int
) -> PromiseToPay:
    return _update_promise_status(promise_id,"broken",actor_id)

def list_promises_for_loan(loan_id: int) -> list[PromiseToPay]:
    get_loan(loan_id)  # institution check enforced internally
    return (
        PromiseToPay.query.filter_by(loan_id=loan_id)
        .order_by(PromiseToPay.created_at.desc())
        .all()
    )