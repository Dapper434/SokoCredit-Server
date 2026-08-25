from decimal import Decimal
from typing import Any, Optional

from extensions import db
from foundations.models import User
from foundations.audit import log_action
from origination.services import set_credit_tier

from underwriting.models import (
    CreditScoreLog,
    Loan,
    LoanApproval,
    CreditScoreLog,
    CREDIT_TIERS,
    utcnow
)

#placeholder tiering for get_available_credit()
TIER_MULTIPLIERS = {
    "A": Decimal("3"),
    "B": Decimal("2"),
    "C": Decimal("1")
}

#Internal helpers

def _require_role(
    user_id:int,
    allowed_roles:tuple[str,...]
) -> User:
    #fetches foundation user and confirms they are authorized to perform the action

    user = db.session.get(User, user_id)
    if user is None:
        raise ValueError(f"No such user for id:{user_id}")

    if user.role not in allowed_roles:
        raise PermissionError(
            f"User {user_id} with role '{user.role}' is authorized for this action "
        )
    return user


def _get_loan_or_404(
    loan_id:int
) -> Loan:
    loan = db.session.get(Loan, loan_id)
    if loan is None:
        raise ValueError(f"No such loan for id {loan_id}")
    return loan

def _get_latest_approval(
    loan:Loan
) -> Optional[LoanApproval]:
    #fetches latest approval for loan
    return (
        LoanApproval.query.filter_by(loan_id = loan.id)
        .order_by(LoanApproval.maker_action_at.desc())
        .first()
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