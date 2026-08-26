from decimal import Decimal
from typing import Any, Optional

from extensions import db
from foundations.models import User
from foundations.auth import AuthError, get_user_institution_id, verify_institution_access
from foundations.audit import log_action
from origination.services import set_credit_tier, get_customer_profile

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
       LoanApproval.query.filter_by(loan_id=loan.id).order_by(LoanApproval.maker_action_at.desc().all())
    )

#Maker-Checker Workflow
#loan_officer creates loan manager/admin aproves loan

def propose_loan(
    actor_id: int,
    customer_profile_id: int,
    lending_institution_id: int,
    principal: Decimal,
    interest_rate: Decimal,
    term_days: int,
    repayment_frequency: str,
    loan_purpose: Optional[str] = None,
    notes: Optional[str] = None,
) -> Loan:
    #loan_officer proposes a loan with initial status="pending" & decision="pending"

    _require_role(actor_id, ("loan_officer",))

    loan = Loan(
        lending_institution_id=lending_institution_id,
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
        lending_institution_id=lending_institution_id,
    )

    return loan

def approve_loan(
    loan_id: int,
    checker_id: int,
    notes: Optional[str]= None
) -> Loan:
    #only manager/admin/superadmin can approve loan
    #only approves loan and passes decision to Servicing.disburse_loan

    loan = _get_loan_or_404(loan_id)
    approval = _get_latest_approval(loan)
    if approval is None or approval.decision != "pending":
        raise ValueError("Loan has no pending approval to act on")

    _require_role(checker_id, ("manager", "admin", "super_admin"))
    if checker_id == approval.maker_id:
        raise PermissionError("the checker cannot be the same as the maker of the loan")

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
    loan = _get_loan_or_404(loan_id)
    approval = _get_latest_approval(loan)
    if approval is None or approval.decision != "pending":
        raise ValueError("Loan has no pending approval to act on")

    _require_role(checker_id, ("manager", "admin", "super_admin"))
    if checker_id == approval.maker_id:
        raise PermissionError("the checker cannot be the same as the maker of the loan")

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

    loan = _get_loan_or_404(loan_id)
    approval = _get_latest_approval(loan)
    if approval is None or approval.desicion != "approved":
        raise ValueError("Loan must be approved before disbursment")

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

    active_loans = Loan.query.filer_by(
        customer_profile_id=customer_profile_id,
        status="active"
    ).all()

    return sum(
     (loan.principal for loan in active_loans), Decimal("0")
    )

#Credit-tiering

def recalculate_credit_score(
    customer_profile_id: int,
    new_tier: str,
    score_components: Optional[dict[str, Any]] = None,
    actor_id: Optional[int] = None,    
) -> CreditScoreLog:
    #rule based logic that decides a new tier based on score components

    if new_tier not in CREDIT_TIERS:
        raise ValueError(f"Invalid tier: {new_tier} must be one of {CREDIT_TIERS}.")

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

    set_credit_tier(customer_profile_id=customer_profile_id, tier=new_tier)

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