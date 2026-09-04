#Servicing module business logic
#Handles disbursement, repayment processing, schedule management, and reschedule requests.
#Other modules should call these functions instead of importing servicing.models directly.

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from extensions import db
from foundations.auth import AuthError, get_user_institution_id, verify_institution_access
from foundations.audit import log_action

from .models import (
    RepaymentSchedule,
    Transaction,
    RescheduleRequest,
    RepaymentScheduleHistory,
    utcnow,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

FREQUENCY_DAYS = {
    "daily": 1,
    "weekly": 7,
    "lump_sum": None,  # single installment at maturity
}


def normalize_interest_rate(rate: Decimal) -> Decimal:
    """Convert a stored interest rate to its decimal form.

    Rates are stored as whole-number percentages (15 means 15%), so anything
    >= 1 is divided by 100. Anything below 1 is assumed to already be decimal.
    Quoting code must call this too, so a customer's quote and the schedule
    they are actually charged can never diverge.
    """
    return rate / Decimal("100") if rate >= 1 else rate


DAYS_IN_YEAR = Decimal("365")


def calculate_loan_totals(
    principal: Decimal,
    annual_rate: Decimal,
    term_days: int,
    num_installments: int,
) -> dict:
    """Single source of truth for what a loan costs and how it splits.

    Interest is the annual rate prorated across the loan's actual term:
        interest        = principal × annual_rate × term_days / 365
        total_repayable = principal + interest

    *annual_rate* may be given either as a stored percentage (32.51) or as a
    decimal fraction (0.3251); it is normalized here so callers cannot get it
    wrong. Everything is Decimal — never float — matching the rest of the
    money handling in this module.

    The final installment absorbs every rounding remainder, so the returned
    parts always re-sum exactly:
        installment_amount × (n-1) + final_installment_amount == total_repayable
        installment_interest × (n-1) + final_installment_interest == interest
    """
    if num_installments < 1:
        raise ValueError("num_installments must be at least 1")

    rate = normalize_interest_rate(annual_rate)
    term = Decimal(term_days) / DAYS_IN_YEAR

    interest = (principal * rate * term).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_repayable = principal + interest

    n = num_installments
    installment_amount = (total_repayable / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    installment_interest = (interest / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # The last installment takes whatever is left, so nothing drifts from the
    # total through independently rounded parts.
    final_installment_amount = total_repayable - (installment_amount * (n - 1))
    final_installment_interest = interest - (installment_interest * (n - 1))

    return {
        "principal": principal,
        "interest": interest,
        "total_repayable": total_repayable,
        "num_installments": n,
        "installment_amount": installment_amount,
        "final_installment_amount": final_installment_amount,
        "installment_interest": installment_interest,
        "final_installment_interest": final_installment_interest,
    }


def _installment_count(repayment_frequency: str, term_days: int) -> int:
    """Installments for a loan — the existing daily/weekly/lump_sum rule."""
    period = FREQUENCY_DAYS.get(repayment_frequency)
    if period is None:
        return 1
    return max(term_days // period, 1)


def _generate_schedule(loan) -> list[RepaymentSchedule]:
    """
    Build flat repayment schedule rows for *loan* and add them to the session.
    Instalment count and spacing follow the loan's repayment frequency; the
    amounts come from calculate_loan_totals(), the one function that also backs
    the customer's pre-application quote, so preview and charge cannot diverge.
    """
    period = FREQUENCY_DAYS.get(loan.repayment_frequency)
    n = _installment_count(loan.repayment_frequency, loan.term_days)

    totals = calculate_loan_totals(
        principal=loan.principal,
        annual_rate=loan.interest_rate,
        term_days=loan.term_days,
        num_installments=n,
    )

    schedules = []

    for i in range(1, n + 1):
        if period is None:
            due_date = loan.disbursed_at.date() + timedelta(days=loan.term_days)
        else:
            due_date = loan.disbursed_at.date() + timedelta(days=period * i)

        if i == n:
            # last instalment absorbs rounding remainder
            inst_total = totals["final_installment_amount"]
            inst_interest = totals["final_installment_interest"]
        else:
            inst_total = totals["installment_amount"]
            inst_interest = totals["installment_interest"]

        # Derived, so each row satisfies total_due == principal_due + interest_due.
        inst_principal = inst_total - inst_interest

        sched = RepaymentSchedule(
            loan_id=loan.id,
            installment_number=i,
            due_date=due_date,
            principal_due=inst_principal,
            interest_due=inst_interest,
            total_due=inst_total,
            amount_paid=Decimal("0"),
            status="pending",
        )
        db.session.add(sched)
        schedules.append(sched)

    return schedules


# ── Disbursement ─────────────────────────────────────────────────────────────

def disburse_loan(loan_id: int, actor_id: int):
    """
    Moves an approved loan into 'active' status:
      1. Validates the loan is approved
      2. Flips status → active, sets disbursed_at & maturity_date
      3. Creates a disbursement Transaction
      4. Generates the repayment schedule
    """
    from underwriting.models import Loan, LoanApproval

    loan = db.session.get(Loan, loan_id)
    if loan is None:
        raise AuthError("No such loan.", 404)

    # Verify the latest approval is "approved"
    approval = (
        LoanApproval.query
        .filter_by(loan_id=loan.id)
        .order_by(LoanApproval.maker_action_at.desc())
        .first()
    )
    if approval is None or approval.decision != "approved":
        raise AuthError("Loan must be approved before disbursement.", 400)

    if loan.status == "active":
        raise AuthError("Loan has already been disbursed.", 400)

    now = utcnow()

    # Flip loan state
    before_status = loan.status
    loan.status = "active"
    loan.disbursed_at = now
    loan.maturity_date = (now + timedelta(days=loan.term_days)).date()

    # Record disbursement transaction
    txn = Transaction(
        loan_id=loan.id,
        amount=loan.principal,
        channel="bank_transfer",
        transaction_type="disbursement",
        status="completed",
    )
    db.session.add(txn)
    db.session.flush()

    # Generate repayment schedule
    _generate_schedule(loan)

    db.session.commit()

    log_action(
        actor_id=actor_id,
        entity_type="Loan",
        entity_id=loan.id,
        action="update",
        before={"status": before_status},
        after={"status": "active", "disbursed_at": str(now)},
        lending_institution_id=loan.lending_institution_id,
    )

    return loan


# ── Repayment Processing ────────────────────────────────────────────────────

def _allocate_payment(loan_id: int, amount: Decimal) -> list[dict]:
    """Waterfall a confirmed payment across the oldest unpaid schedule rows.

    Mutates RepaymentSchedule rows and flips the loan to 'fully_paid' when every
    row is settled. Does NOT create a Transaction or commit — the caller owns
    that, so this is reusable by both the manual path and the STK-callback path.
    Returns the allocation breakdown.
    """
    from underwriting.models import Loan

    loan = db.session.get(Loan, loan_id)
    remaining = Decimal(str(amount))
    now = utcnow()
    allocation: list[dict] = []

    schedules = (
        RepaymentSchedule.query
        .filter_by(loan_id=loan_id)
        .filter(RepaymentSchedule.status.in_(("pending", "overdue", "partial")))
        .order_by(RepaymentSchedule.installment_number.asc())
        .all()
    )

    for sched in schedules:
        if remaining <= 0:
            break
        owed = sched.total_due - sched.amount_paid
        if owed <= 0:
            continue

        applied = min(remaining, owed)
        sched.amount_paid += applied
        remaining -= applied

        if sched.amount_paid >= sched.total_due:
            sched.status = "paid"
            sched.paid_at = now
        else:
            sched.status = "partial"

        allocation.append({
            "schedule_id": sched.id,
            "installment_number": sched.installment_number,
            "applied": str(applied),
        })

    all_schedules = RepaymentSchedule.query.filter_by(loan_id=loan_id).all()
    if all_schedules and all(s.status == "paid" for s in all_schedules):
        loan.status = "fully_paid"

    return allocation


def process_repayment(
    loan_id: int,
    amount: Decimal,
    channel: str,
    gateway_reference: str,
) -> Optional[Transaction]:
    """
    Record a confirmed repayment (manual/staff entry). Waterfall-allocates it
    and writes a completed Transaction. Returns None if the gateway_reference
    was already processed.
    """
    from underwriting.models import Loan

    loan = db.session.get(Loan, loan_id)
    if loan is None:
        raise AuthError("No such loan.", 404)

    if gateway_reference:
        existing = Transaction.query.filter_by(gateway_reference=gateway_reference).first()
        if existing is not None:
            return None

    amount = Decimal(str(amount))
    allocation = _allocate_payment(loan_id, amount)

    txn = Transaction(
        loan_id=loan_id,
        amount=amount,
        channel=channel,
        gateway_reference=gateway_reference,
        transaction_type="repayment",
        status="completed",
        allocation_breakdown=allocation,
    )
    db.session.add(txn)
    db.session.commit()

    return txn


# ── M-Pesa STK repayment ────────────────────────────────────────────────────

def _next_amount_due(loan_id: int) -> Decimal:
    """Balance remaining on the earliest unpaid installment."""
    row = (
        RepaymentSchedule.query
        .filter_by(loan_id=loan_id)
        .filter(RepaymentSchedule.status.in_(("pending", "overdue", "partial")))
        .order_by(RepaymentSchedule.installment_number.asc())
        .first()
    )
    if row is None:
        return Decimal("0")
    return row.total_due - row.amount_paid


def initiate_repayment_stk(loan_id: int, customer_profile_id: int) -> Transaction:
    """Fire a Sandbox STK push for the loan's next installment.

    Creates a pending Transaction carrying the CheckoutRequestID; the real
    result arrives later via handle_stk_callback().
    """
    from underwriting.models import Loan
    from origination.models import CustomerProfile
    from servicing.mpesa.config import resolve_config, callback_base_url
    from servicing.mpesa.client import stk_push
    from servicing.mpesa.security import callback_path

    loan = db.session.get(Loan, loan_id)
    if loan is None:
        raise AuthError("No such loan.", 404)
    if loan.customer_profile_id != customer_profile_id:
        raise AuthError("You do not have permission to pay this loan.", 403)
    if loan.status not in ("active", "overdue"):
        raise AuthError("This loan is not open for repayment.", 400)

    amount = _next_amount_due(loan_id)
    if amount <= 0:
        raise AuthError("This loan has no outstanding installment.", 400)

    profile = db.session.get(CustomerProfile, customer_profile_id)
    if not profile or not profile.phone_number:
        raise AuthError("No M-Pesa phone number on your profile.", 400)

    cfg = resolve_config(loan.lending_institution_id)  # raises MpesaConfigError if unset
    resp = stk_push(
        cfg,
        phone=profile.phone_number,
        amount=amount,
        account_reference=f"LN{loan_id}",
        description="Loan repayment",
        callback_url=f"{callback_base_url()}{callback_path('stk')}",
    )

    txn = Transaction(
        loan_id=loan_id,
        amount=amount,
        channel="mpesa",
        transaction_type="repayment",
        status="pending",
        checkout_request_id=resp["CheckoutRequestID"],
        merchant_request_id=resp.get("MerchantRequestID"),
    )
    db.session.add(txn)
    db.session.commit()
    return txn


def get_repayment_transaction(checkout_request_id: str) -> Optional[Transaction]:
    return Transaction.query.filter_by(checkout_request_id=checkout_request_id).first()


def _confirm_repayment(txn: Transaction, parsed) -> None:
    """Apply a successful STK result to a pending repayment Transaction."""
    if txn.status != "pending":
        return  # already reconciled — idempotent

    txn.status = "completed"
    txn.gateway_reference = parsed.mpesa_receipt
    txn.raw_callback = parsed.as_dict()
    paid = parsed.amount if parsed.amount is not None else txn.amount
    txn.amount = paid
    txn.allocation_breakdown = _allocate_payment(txn.loan_id, paid)
    db.session.commit()


def _fail_transaction(txn: Transaction, parsed) -> None:
    if txn.status != "pending":
        return
    txn.status = "failed"
    txn.failure_reason = parsed.result_desc[:255]
    db.session.commit()


def handle_stk_callback(body: dict) -> dict:
    """Shared entry point for every STK result callback (repayment + savings).

    Parses once, then dispatches by which pending record owns the
    CheckoutRequestID. Returns the ack body Safaricom expects.
    """
    from servicing.mpesa.callbacks import parse_stk_callback, CallbackParseError

    try:
        parsed = parse_stk_callback(body)
    except CallbackParseError as exc:
        return {"ResultCode": 1, "ResultDesc": f"Rejected: {exc}"}

    crid = parsed.checkout_request_id

    txn = Transaction.query.filter_by(checkout_request_id=crid).first()
    if txn is not None:
        if parsed.succeeded:
            _confirm_repayment(txn, parsed)
        else:
            _fail_transaction(txn, parsed)
        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    # Not a repayment — hand to Origination's savings reconciliation.
    from origination.services import confirm_savings_deposit_callback
    if confirm_savings_deposit_callback(parsed):
        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    return {"ResultCode": 1, "ResultDesc": "Unknown CheckoutRequestID"}


# ── Schedule Retrieval ───────────────────────────────────────────────────────

def get_loan_schedule(loan_id: int) -> list[RepaymentSchedule]:
    """Returns all repayment schedule rows for a loan, ordered by instalment number."""
    return (
        RepaymentSchedule.query
        .filter_by(loan_id=loan_id)
        .order_by(RepaymentSchedule.installment_number.asc())
        .all()
    )


# ── Reschedule Requests ─────────────────────────────────────────────────────

def request_reschedule(
    loan_id: int,
    requested_by: int,
    reason_category: str,
    requested_mode: str,
    requested_extension_days: int,
) -> RescheduleRequest:
    """
    Creates a reschedule request for an active loan.
    The request starts in 'pending' state and must be approved by a branch_manager.
    """
    from underwriting.models import Loan

    loan = db.session.get(Loan, loan_id)
    if loan is None:
        raise AuthError("No such loan.", 404)

    if loan.status != "active":
        raise AuthError("Only active loans can be rescheduled.", 400)

    req = RescheduleRequest(
        loan_id=loan_id,
        requested_by=requested_by,
        reason_category=reason_category,
        requested_mode=requested_mode,
        requested_extension_days=requested_extension_days,
        admin_decision="pending",
    )
    db.session.add(req)
    db.session.commit()

    log_action(
        actor_id=requested_by,
        entity_type="RescheduleRequest",
        entity_id=req.id,
        action="create",
        before=None,
        after={"loan_id": loan_id, "mode": requested_mode, "days": requested_extension_days},
        lending_institution_id=loan.lending_institution_id,
    )

    return req


# ── Outstanding Balance ─────────────────────────────────────────────────────

def get_outstanding_balance(loan_id: int) -> Decimal:
    """
    Calculates the outstanding balance for a loan by summing up
    (total_due − amount_paid) across all unpaid schedule rows.
    """
    schedules = (
        RepaymentSchedule.query
        .filter_by(loan_id=loan_id)
        .filter(RepaymentSchedule.status.in_(("pending", "overdue", "partial")))
        .all()
    )
    return sum(
        (s.total_due - s.amount_paid for s in schedules),
        Decimal("0"),
    )
