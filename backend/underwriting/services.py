from datetime import date
from decimal import Decimal
from typing import Any, Optional

from extensions import db
from foundations.auth import AuthError, get_user_institution_id, verify_institution_access
from foundations.audit import log_action
from origination.services import set_credit_tier, get_customer_profile
from underwriting.scoring import compute_credit_tier

from underwriting.models import (
    LOAN_STATUSES,
    Loan,
    LoanApproval,
    SavingsAccount,
    CreditScoreLog,
    CREDIT_TIERS,
    OPEN_LOAN_STATUSES,
    utcnow,
)

# Distinct savings days a customer must reach before their institution's full
# limit unlocks. Below it everyone is held to the platform starter limit.
FULL_LIMIT_SAVINGS_DAYS = 30
STARTER_CREDIT_LIMIT = Decimal("15000")

#placeholder tiering for get_available_credit()
TIER_MULTIPLIERS = {
    "A": Decimal("3"),
    "B": Decimal("2"),
    "C": Decimal("1")
}

#Internal helpers
def _get_latest_approval(
    loan:Loan
) -> Optional[LoanApproval]:
    #fetches latest approval for loan
    return (
        LoanApproval.query.filter_by(loan_id = loan.id)
        .order_by(LoanApproval.maker_action_at.desc())
        .first()
    )

#Reads

def get_loan(
    loan_id:int
) -> Loan:
    loan = db.session.get(Loan, loan_id)
    if loan is None:
        raise AuthError("No such loan.", 404)
    verify_institution_access(loan.lending_institution_id)
    return loan

def list_loan_approvals(
    loan_id: int
) -> list[LoanApproval]:
    loan = get_loan(loan_id)
    return (
       LoanApproval.query.filter_by(loan_id=loan.id).order_by(LoanApproval.maker_action_at.desc()).all()
    )

#Maker-Checker Workflow
#loan_officer creates loan branch_manager approves loan

def propose_loan(
    actor_id: int,
    customer_profile_id: int,
    principal: Decimal,
    interest_rate: Decimal,
    term_days: int,
    repayment_frequency: str,
    loan_purpose: Optional[str] = None,
    notes: Optional[str] = None,
) -> Loan:
    #loan_officer proposes a loan with initial status="pending" & decision="pending"

    institution_id = get_user_institution_id(actor_id)
    if institution_id is None:
        raise AuthError("No such staff user, or user has no institution.", 400)

    get_customer_profile(customer_profile_id)

    loan = Loan(
        lending_institution_id=institution_id,
        customer_profile_id=customer_profile_id,
        principal=principal,
        interest_rate=interest_rate,
        term_days=term_days,
        repayment_frequency=repayment_frequency,
        loan_purpose=loan_purpose,
        status="pending",
    )
    db.session.add(loan)
    db.session.flush() #assigns loan.id without commiting to allow approval to reference it

    approval = LoanApproval(
        loan_id=loan.id,
        maker_id=actor_id,
        maker_notes=notes,
        decision="pending",
    )

    db.session.add(approval)
    db.session.commit()

    #log proposed loan action
    log_action(
        actor_id=actor_id,
        entity_type="Loan",
        entity_id=loan.id,
        action="create",
        before=None,
        after={
            "customer_profile_id": customer_profile_id,
            "principal": str(principal),
            "status": loan.status,
        },
        lending_institution_id=institution_id,
    )

    return loan

def apply_for_loan(
    actor_id: int,
    customer_profile_id: int,
    principal: Decimal,
    term_days: int,
    repayment_frequency: str,
    loan_purpose: Optional[str] = None,
) -> Loan:
    # customer applies for a loan
    institution_id = get_user_institution_id(actor_id)
    if institution_id is None:
        raise AuthError("User has no institution.", 400)

    # 1. 14-day savings gate check
    savings_account = SavingsAccount.query.filter_by(customer_profile_id=customer_profile_id).first()
    if savings_account is None or not savings_account.is_savings_mature:
        raise AuthError("You must maintain a savings account for 14 days before applying for a loan.", 403)

    # 1b. One open loan at a time — a customer must settle their current loan
    # before applying for another.
    open_loan = Loan.query.filter(
        Loan.customer_profile_id == customer_profile_id,
        Loan.status.in_(OPEN_LOAN_STATUSES),
    ).first()
    if open_loan is not None:
        raise AuthError(
            "You already have a loan in progress. Repay it in full before applying for another.",
            409,
        )


    # 2. Available credit. Exceeding it is NOT a rejection — the request still
    # goes to the Approval Desk (as every application already does), carrying a
    # snapshot of the limit so a reviewer can see it was an over-limit ask.
    # The institution's max_loan_limit remains a hard ceiling.
    available = get_available_credit(customer_profile_id)
    institution_ceiling = get_institution_max_loan_limit(institution_id)
    if principal > institution_ceiling:
        raise AuthError(
            f"Requested amount ({principal}) exceeds this institution's maximum "
            f"loan limit ({institution_ceiling}).",
            400,
        )

    interest_rate = get_default_interest_rate(institution_id)

    loan = Loan(
        lending_institution_id=institution_id,
        customer_profile_id=customer_profile_id,
        principal=principal,
        interest_rate=interest_rate,
        term_days=term_days,
        repayment_frequency=repayment_frequency,
        loan_purpose=loan_purpose,
        status="pending",
        available_credit_at_application=available,
    )
    db.session.add(loan)
    db.session.flush()

    approval = LoanApproval(
        loan_id=loan.id,
        maker_id=actor_id,
        decision="pending",
    )
    db.session.add(approval)
    db.session.commit()

    log_action(
        actor_id=actor_id,
        entity_type="Loan",
        entity_id=loan.id,
        action="create",
        before=None,
        after={
            "customer_profile_id": customer_profile_id,
            "principal": str(principal),
            "status": loan.status,
        },
        lending_institution_id=institution_id,
    )

    return loan

def approve_loan(
    loan_id: int,
    checker_id: int,
    notes: Optional[str]= None
) -> Loan:
    #only branch_manager can approve loan
    #only approves loan and passes decision to Servicing.disburse_loan

    loan = get_loan(loan_id)
    approval = _get_latest_approval(loan)
    if approval is None or approval.decision != "pending":
        raise AuthError("Loan has no pending approval to act on", 400)

    if checker_id == approval.maker_id:
        raise AuthError("the checker cannot be the same as the maker of the loan", 403)

    before = {"decision": approval.decision}
    approval.checker_id = checker_id
    approval.checker_notes = notes
    approval.decision = "approved"
    approval.checker_action_at = utcnow()
    db.session.commit()
 
    log_action(
        actor_id=checker_id,
        entity_type="LoanApproval",
        entity_id=approval.id,
        action="update",
        before=before,
        after={"decision": "approved"},
        lending_institution_id=loan.lending_institution_id,
    )
 
    return loan

def reject_loan(
    loan_id:int,
    checker_id:int,
    notes:Optional[str] = None
) -> Loan:
    loan = get_loan(loan_id)
    approval = _get_latest_approval(loan)
    if approval is None or approval.decision != "pending":
        raise AuthError("Loan has no pending approval to act on", 400)

    if checker_id == approval.maker_id:
        raise AuthError("the checker cannot be the same as the maker of the loan", 403)

    before = {"decision": approval.decision, "loan_status": loan.status}
    approval.checker_id = checker_id
    approval.checker_notes = notes
    approval.decision = "rejected"
    approval.checker_action_at = utcnow()
    # Mark the loan itself, so the customer's portfolio can show the outcome and
    # a rejected request stops counting as an open loan.
    loan.status = "rejected"
    db.session.commit()

    log_action(
        actor_id=checker_id,
        entity_type="LoanApproval",
        entity_id=approval.id,
        action="update",
        before=before,
        after={"decision": "rejected", "loan_status": "rejected"},
        lending_institution_id=loan.lending_institution_id,
    )

    return loan

def disburse_loan(
    loan_id: int,
    actor_id:int
) -> Loan:
    #Underwriting calls into Servicing to move the money
    #writes into disbursed_at and flips status to active
    #depends on Servicing module so is a stub as for now

    loan = get_loan(loan_id)
    # 1. Ensure loan is approved
    approval = _get_latest_approval(loan)
    if approval is None or approval.decision != "approved":
        raise AuthError("Loan must be approved before disbursment", 400)

    # 2. Call Servicing to move the money and update the loan status
    from servicing.services import disburse_loan as servicing_disburse
    return servicing_disburse(loan.id, actor_id)

# Applied when an institution has not configured its own rate. Both the loan
# application and the customer's quote resolve through get_default_interest_rate,
# so this fallback can never be applied in one place but not the other.
DEFAULT_INTEREST_RATE = Decimal("5.0")


def get_default_interest_rate(institution_id: int) -> Decimal:
    """The interest rate an institution charges, as a whole-number percentage.

    Single source of truth for both the rate written onto a new Loan and the
    rate quoted to the customer beforehand.
    """
    from foundations.models import LendingInstitution

    institution = db.session.get(LendingInstitution, institution_id)
    if institution is not None and institution.default_interest_rate is not None:
        return Decimal(str(institution.default_interest_rate))
    return DEFAULT_INTEREST_RATE


def get_available_credit(
    customer_profile_id:int
) -> Decimal:
    #derived never stored
    #is_savings_mature must be true or new customers get 0
    #branch_managers can disburse exceptional first loans
    #FORMULA - (tier_multiplier * total_savings) - sum(outstanding_balance)
    # then capped: STARTER_CREDIT_LIMIT under 30 savings days, otherwise the
    # institution's own max_loan_limit.

    profile = get_customer_profile(customer_profile_id)

    savings_account = SavingsAccount.query.filter_by(
        customer_profile_id=customer_profile_id
    ).first()

    # We allow the preview of available credit even before savings are mature
    # so the customer can watch it grow during the 14-day check-in period.
    if savings_account is None:
        return Decimal("0")

    latest_score = (
        CreditScoreLog.query.filter_by(customer_profile_id=customer_profile_id)
        .order_by(CreditScoreLog.calculated_at.desc())
        .first()
    )

    # If no credit score exists yet, default to Tier C (multiplier 1)
    tier = latest_score.new_tier if latest_score else "C"
    multiplier = TIER_MULTIPLIERS.get(tier, Decimal("0"))
    gross_limit = multiplier * savings_account.total_savings_balance

    outstanding = _get_total_outstanding_balance(customer_profile_id)

    available = gross_limit - outstanding
    if available <= 0:
        return Decimal("0")

    available = min(available, _credit_ceiling(profile))
    return available if available > 0 else Decimal("0")


def _credit_ceiling(profile) -> Decimal:
    """The maximum available credit this customer may be shown or granted.

    Under FULL_LIMIT_SAVINGS_DAYS distinct savings days every customer is held
    to the platform starter limit, whatever their institution or tier. Once
    past it, the institution's own max_loan_limit applies.
    """
    from origination.services import get_checkin_count

    # Counts savings check-in rows, which the uq_savings_checkin_per_day
    # constraint guarantees is exactly the count of distinct check-in dates —
    # the same measure the 14-day mandatory gate uses. Cumulative days, not a
    # consecutive-day streak.
    savings_days = get_checkin_count(profile.id)
    if savings_days < FULL_LIMIT_SAVINGS_DAYS:
        return STARTER_CREDIT_LIMIT

    return get_institution_max_loan_limit(profile.lending_institution_id)


def get_institution_max_loan_limit(institution_id: int) -> Decimal:
    """An institution's ceiling on a single customer's available credit.

    Raises rather than falling back to a global default: a silently-applied
    wrong default is what caused the interest-rate mismatch, so an unseeded
    institution must fail loudly instead of quietly lending on the wrong terms.
    """
    from foundations.models import LendingInstitution

    institution = db.session.get(LendingInstitution, institution_id)
    if institution is None:
        raise AuthError(f"No such lending institution ({institution_id}).", 404)
    if institution.max_loan_limit is None:
        raise AuthError(
            f"Institution {institution_id} has no max_loan_limit configured. "
            "Seed it before lending (see seed_loan_limits.py).",
            500,
        )
    return Decimal(str(institution.max_loan_limit))

def _get_total_outstanding_balance(
    customer_profile_id: int
) -> Decimal:
    from servicing.services import get_outstanding_balance

    active_loans = Loan.query.filter_by(
        customer_profile_id=customer_profile_id,
        status="active"
    ).all()

    return sum(
     (get_outstanding_balance(loan.id) for loan in active_loans), Decimal("0")
    )

#Credit-tiering

def recalculate_credit_score(
    customer_profile_id: int,
    new_tier: str,
    score_components: Optional[dict[str, Any]] = None,
    actor_id: Optional[int] = None,    
) -> CreditScoreLog:
    #rule based logic that decides a new tier based on score components

    get_customer_profile(customer_profile_id)

    if new_tier not in CREDIT_TIERS:
        raise AuthError(f"Invalid tier: {new_tier} must be one of {CREDIT_TIERS}.", 400)

    latest = (
        CreditScoreLog.query.filter_by(customer_profile_id=customer_profile_id)
        .order_by(CreditScoreLog.calculated_at.desc())
        .first()
    )

    previous_tier = latest.new_tier if latest else None

    entry = CreditScoreLog(
        customer_profile_id=customer_profile_id,
        previous_tier=previous_tier,
        new_tier=new_tier,
        score_components=score_components,
    )
    db.session.add(entry)
    db.session.commit()

    set_credit_tier(customer_profile_id=customer_profile_id, tier=new_tier, actor_id=actor_id)

    if actor_id is not None:
        institution_id = get_user_institution_id(actor_id)
        log_action(
            actor_id=actor_id,
            entity_type="CreditScoreLog",
            entity_id=entry.id,
            action="create",
            before={"tier": previous_tier},
            after={"tier": new_tier},
            lending_institution_id=institution_id,
        )

    return entry

# ── Teammate additions (Collections / scoring / Servicing→Underwriting callbacks) ──
# Ported from the SokoCredit clean branch during the Dev→clean merge. These are
# additive; the rest of this module is the Dev source of truth.

def determine_and_recalculate_credit_score(
    customer_profile_id: int,
    actor_id: Optional[int] = None,
) -> CreditScoreLog:
    """Recompute a customer's tier from their repayment/savings history.

    Still a stub: on_time_rate, completed_loan_cycles, has_default and
    reschedule_count need a Servicing stats function that isn't wired yet.
    """
    raise NotImplementedError("Servicing repayment-stats feed not wired yet.")


def get_loans_due(
    actor_id: int,
    only_mine: bool = True,
    as_of_date=None,
) -> list[Loan]:
    """Active loans in the caller's institution whose maturity_date has passed.
    only_mine restricts to loans whose customer is assigned to actor_id.
    """
    if as_of_date is None:
        as_of_date = date.today()

    institution_id = get_user_institution_id(actor_id)
    if institution_id is None:
        raise AuthError("No such staff user, or user has no institution.", 400)

    candidates = Loan.query.filter(
        Loan.lending_institution_id == institution_id,
        Loan.status == "active",
        Loan.maturity_date <= as_of_date,
    ).all()

    if not only_mine:
        return candidates
    return [
        loan for loan in candidates
        if get_customer_profile(loan.customer_profile_id).user_id == actor_id
    ]


def _get_loan_unscoped(loan_id: int) -> Loan:
    """System-level loan fetch with no institution/JWT check — for webhooks and
    background jobs that have no authenticated user."""
    loan = db.session.get(Loan, loan_id)
    if loan is None:
        raise AuthError("No such loan.", 404)
    return loan


def mark_loan_fully_paid(loan_id: int, actor_id: Optional[int] = None) -> Loan:
    """Called by Servicing once a loan's schedule is fully settled."""
    loan = _get_loan_unscoped(loan_id)
    if loan.status != "active":
        raise AuthError(f"Cannot mark a loan as fully_paid from status '{loan.status}'.", 400)
    before = {"status": loan.status}
    loan.status = "fully_paid"
    db.session.commit()
    log_action(
        actor_id=actor_id, entity_type="Loan", entity_id=loan.id, action="update",
        before=before, after={"status": "fully_paid"},
        lending_institution_id=loan.lending_institution_id,
    )
    return loan


def mark_loan_defaulted(loan_id: int, actor_id: Optional[int] = None) -> Loan:
    """Called by Servicing once its default-detection flags a loan."""
    loan = _get_loan_unscoped(loan_id)
    if loan.status not in ("active", "restructured"):
        raise AuthError(f"Cannot mark a loan as defaulted from status '{loan.status}'.", 400)
    before = {"status": loan.status}
    loan.status = "defaulted"
    db.session.commit()
    log_action(
        actor_id=actor_id, entity_type="Loan", entity_id=loan.id, action="update",
        before=before, after={"status": "defaulted"},
        lending_institution_id=loan.lending_institution_id,
    )
    return loan


def mark_loan_restructured(loan_id: int, actor_id: Optional[int] = None) -> Loan:
    """Called by Servicing once a reschedule request is approved and applied."""
    loan = _get_loan_unscoped(loan_id)
    if loan.status != "active":
        raise AuthError(f"Cannot mark a loan as restructured from status '{loan.status}'.", 400)
    before = {"status": loan.status}
    loan.status = "restructured"
    db.session.commit()
    log_action(
        actor_id=actor_id, entity_type="Loan", entity_id=loan.id, action="update",
        before=before, after={"status": "restructured"},
        lending_institution_id=loan.lending_institution_id,
    )
    return loan


def list_loans_for_institution(
    actor_id: int,
    status_filter: Optional[str] = None,
) -> list[Loan]:
    """Every loan in the caller's institution — the full book for Analytics and
    Collections portfolio-wide metrics (GLP, PAR). Not restricted by status."""
    institution_id = get_user_institution_id(actor_id)
    if institution_id is None:
        raise AuthError("No such staff user, or user has no institution.", 400)

    if status_filter is not None and status_filter not in LOAN_STATUSES:
        raise AuthError(f"Invalid status filter '{status_filter}'", 400)

    query = Loan.query.filter_by(lending_institution_id=institution_id)
    if status_filter is not None:
        query = query.filter_by(status=status_filter)
    return query.all()
