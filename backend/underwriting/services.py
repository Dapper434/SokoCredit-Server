from datetime import date
from decimal import Decimal
from typing import Any, Optional

from extensions import db
from foundations.auth import AuthError, get_user_institution_id, verify_institution_access
from foundations.audit import log_action
from origination.services import set_credit_tier, get_customer_profile
from underwriting.scoring import compute_credit_tier

from underwriting.models import (
    Loan,
    LoanApproval,
    SavingsAccount,
    CreditScoreLog,
    CREDIT_TIERS,
    utcnow,
)

#placeholder tiering for get_available_credit()
TIER_MULTIPLIERS = {
    "A": Decimal("3"),
    "B": Decimal("2"),
    "C": Decimal("1")
}

#minimum savings balance to earn higher "mature" scoring

SAVINGS_BALANCE_THRESHOLD = Decimal("5000")

def compute_credit_tier(
    on_time_rate: Decimal,
    completed_loan_cycles: int,
    has_default: bool,
    reschedule_count: int,
    is_savings_mature: bool,
    savings_balance: Decimal,      
) -> str:

    if has_default:
        return "C"

    points = 0

    if on_time_rate >= Decimal("0.95"):
        points += 40
    elif on_time_rate >= Decimal("0.80"):
        points += 25
    elif on_time_rate >= Decimal("0.60"):
        points += 10

    if completed_loan_cycles >= 3:
        points += 30
    elif completed_loan_cycles >= 1:
        points += 15

    if is_savings_mature and savings_balance >= SAVINGS_BALANCE_THRESHOLD:
        points += 20
    elif is_savings_mature:
        points += 10

    if reschedule_count >= 0:
        points += 10
    elif reschedule_count >= 2:
        points -= 10

    if points >= 70:
        return "A"
    elif points >= 40:
        return "B"
    return "C"


def determine_and_recalculate_credit_score(
   customer_profile_id: int,
   actor_id: Optional[int] = None,     
) -> CreditScoreLog:
   """
   stub
   blocked because on_time_rate, completed_loan_cycles, has_default, reschedule_count, is_savings_mature, savings_balance are not available
   requires Servicing module

   from servicing.services import get_repayment_stats
    stats = get_repayment_stats(customer_profile_id)
    savings = SavingsAccount.query.filter_by(
        customer_profile_id=customer_profile_id).first()
    new_tier = compute_credit_tier(
        on_time_rate=stats.on_time_rate,
        completed_loan_cycles=stats.completed_cycles,
        has_default=stats.has_default,
        reschedule_count=stats.reschedule_count,
        is_savings_mature=savings.is_savings_mature if savings else False,
        savings_balance=savings.total_savings_balance if savings else Decimal("0"),
    )
    return recalculate_credit_score(
        customer_profile_id, new_tier,
        score_components={...},  # the raw inputs above, for the audit trail
        actor_id=actor_id,
    )
   """

   raise NotImplementedError(
       "Servicing module not built yet."
   )

    
#----------------Internal helpers---------------
def _get_latest_approval(
    loan:Loan
) -> Optional[LoanApproval]:
    #fetches latest approval for loan
    return (
        LoanApproval.query.filter_by(loan_id = loan.id)
        .order_by(LoanApproval.maker_action_at.desc())
        .first()
    )

#-----------------Reads--------------------

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
       LoanApproval.query.filter_by(loan_id=loan.id).order_by(LoanApproval.maker_action_at.desc().all())
    )

def get_loans_due(
    actor_id: int,
    only_mine:bool = True,
    as_of_date=None
) -> list[Loan]:
    """
    loan_officer visits this and views the current loans that are due
    only_mine = True restricts loans to whose customer is currently assigned to actor_id
    Due = active loans whose maturity_date has arrived or passed.
    """
    if as_of_date is None:
        as_of_date = date.today()

    institution_id = get_user_institution_id(actor_id)
    if institution_id is None:
        raise AuthError("No such staff user, or user has no institution.", 400)

    candidates = Loan.query.filter(
        Loan.lending_institution_id == institution_id,
        Loan.status == "active",
        Loan.maturity_date <= as_of_date
    ).all()

    if not only_mine:
        return candidates

    return [
        loan for loan in candidates if get_customer_profile(loan.customer_profile_id).user_id == actor_id
    ]

def _get_loan_unscoped(loan_id:int) -> Loan:
    """
    system level fetch with no institution check via JWT
    meant for webhooks with no jwt at all
    """
    loan = db.session.get(Loan,loan_id)
    if loan is None:
        raise AuthError("No such loan.", 404)
    return loan

def mark_loan_fully_paid(
    loan_id:int,
    actor_id: Optional[int] = None
) -> Loan:
    #called by servicing once a loan is fully paid
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
    """
    Called by Servicing once its own default-detection logic flags a loan.
    """
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
    """
    Called by Servicing once a reschedule_request is approved
    (admin_decision == "approve") and actually applied.
    """
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




#Maker-Checker Workflow
#loan_officer creates loan manager/admin approves loan

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

def approve_loan(
    loan_id: int,
    checker_id: int,
    notes: Optional[str]= None
) -> Loan:
    #only manager/admin/super-admin can approve loan
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

    before = {"decision": approval.decision}
    approval.checker_id = checker_id
    approval.checker_notes = notes
    approval.decision = "rejected"
    approval.checker_action_at = utcnow()
    db.session.commit()
 
    log_action(
        actor_id=checker_id,
        entity_type="LoanApproval",
        entity_id=approval.id,
        action="update",
        before=before,
        after={"decision": "rejected"},
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
    approval = _get_latest_approval(loan)
    if approval is None or approval.decision != "approved":
        raise AuthError("Loan must be approved before disbursment", 400)

    raise NotImplementedError(
        "Servicing module not built yet."
    )

def get_available_credit(
    customer_profile_id:int
) -> Decimal:
    #derived never stored
    #is_savings_mature must be true or new customers get 0
    #managers can disburse exceptional first loans
    #FORMULA - (tier_multiplier * total_savings) - sum(outstanding_balance)

    get_customer_profile(customer_profile_id)

    savings_account = SavingsAccount.query.filter_by(
        customer_profile_id=customer_profile_id
    ).first()

    if savings_account is None or not savings_account.is_savings_mature:
        return Decimal("0")

    latest_score = (
        CreditScoreLog.query.filter_by(customer_profile_id=customer_profile_id)
        .order_by(CreditScoreLog.calculated_at.desc())
        .first()
    )

    if latest_score is None:
        return Decimal("0")

    multiplier = TIER_MULTIPLIERS.get(latest_score.new_tier, Decimal("0"))
    gross_limit = multiplier * savings_account.total_savings_balance

    outstanding = _get_total_outstanding_balance(customer_profile_id)
 
    available = gross_limit - outstanding
    return available if available > 0 else Decimal("0")

def _get_total_outstanding_balance(
    customer_profile_id: int
) -> Decimal:
    #stub for now
    #calls servicing.services_get_outstanding_balance per active loan
    #sums the results to grow customer's available credit limit

    active_loans = Loan.query.filter_by(
        customer_profile_id=customer_profile_id,
        status="active"
    ).all()

    return sum(
     (loan.principal for loan in active_loans), Decimal("0")
    )

#Credit-tiering

def recalculate_credit_score(
    customer_profile_id: int,
    on_time_rate: Decimal,
    completed_loan_cycles: int,
    has_defaulted_loan: bool,
    reschedule_count: int,
    actor_id: Optional[int] = None,    
) -> CreditScoreLog:
    #rule based logic that decides a new tier based on score components
    #calls compute_credit_tier
    #Savings inputs (is_savings_mature, savings_balance) pulled from SavingsAccount
    #remaining inputs called from Servicing module (on_time_rate, completed_loan_cycles, has_default, reschedule_count)

    get_customer_profile(customer_profile_id)
    #enforce institution access

    savings_account = SavingsAccount.query.filter_by(
        customer_profile_id=customer_profile_id
    ).first()

    is_savings_mature = savings_account.is_savings_mature if savings_account else False

    savings_balance = savings_account.total_savings_balance if savings_account else Decimal("0")

    new_tier, score_components = compute_credit_tier(
        on_time_rate=on_time_rate,
        completed_loan_cycles=completed_loan_cycles,
        has_defaulted_loan=has_defaulted_loan,
        reschedule_count=reschedule_count,
        is_savings_mature=is_savings_mature,
        savings_balance=savings_balance,
    )

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

    set_credit_tier(
        customer_profile_id=customer_profile_id,
        tier=new_tier,
        actor_id=actor_id,
    )

    if actor_id is not None:
        log_action(
            actor_id=actor_id,
            entity_type="CreditScoreLog",
            entity_id=entry.id,
            action="create",
            before={"tier": previous_tier},
            after={"tier": new_tier},
        )

    return entry