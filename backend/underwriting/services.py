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

