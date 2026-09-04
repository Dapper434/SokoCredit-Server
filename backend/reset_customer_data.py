"""Reset one customer's transactional history back to a clean slate.

Clears savings check-ins, loans, repayments and SokoPoints so the savings
gate and its point award can be exercised again from zero. The customer's
profile, KYC, documents, stall assignment and login are left untouched.

Usage:  .venv/bin/python reset_customer_data.py <customer_profile_id>
        .venv/bin/python reset_customer_data.py 2          # Faith Mauti

Replaces the older clear_faith_data.py / wipe_faith.py, which import a
`savings` module and a `foundations.database` that do not exist.
"""
import sys

from app import create_app
from extensions import db
from foundations.models import User
from origination.models import (
    CustomerProfile,
    SavingsCheckin,
    LoyaltyPoints,
    LoyaltyEvent,
    CustomerBadge,
)
from underwriting.models import SavingsAccount, Loan, CreditScoreLog
from servicing.models import RepaymentSchedule, Transaction


def reset(profile_id: int) -> None:
    profile = db.session.get(CustomerProfile, profile_id)
    if profile is None:
        sys.exit(f"No customer profile with id={profile_id}.")

    user = db.session.get(User, profile.user_id)
    name = user.full_name if user else "(unknown)"
    print(f"Resetting transactional data for {name} (profile_id={profile_id})\n")

    # Loan-scoped children first, so nothing is orphaned by the loan delete.
    loan_ids = [l.id for l in Loan.query.filter_by(customer_profile_id=profile_id).all()]
    schedules = transactions = 0
    if loan_ids:
        transactions = Transaction.query.filter(
            Transaction.loan_id.in_(loan_ids)).delete(synchronize_session=False)
        schedules = RepaymentSchedule.query.filter(
            RepaymentSchedule.loan_id.in_(loan_ids)).delete(synchronize_session=False)

    counts = {
        "transactions": transactions,
        "repayment_schedules": schedules,
        "loans": Loan.query.filter_by(customer_profile_id=profile_id).delete(),
        "credit_score_log": CreditScoreLog.query.filter_by(customer_profile_id=profile_id).delete(),
        "savings_checkins": SavingsCheckin.query.filter_by(customer_profile_id=profile_id).delete(),
        "loyalty_events": LoyaltyEvent.query.filter_by(customer_profile_id=profile_id).delete(),
        "loyalty_points": LoyaltyPoints.query.filter_by(customer_profile_id=profile_id).delete(),
        "customer_badges": CustomerBadge.query.filter_by(customer_profile_id=profile_id).delete(),
    }

    # Reset rather than delete the savings account, so the customer can save again.
    account = SavingsAccount.query.filter_by(customer_profile_id=profile_id).first()
    if account:
        account.total_savings_balance = 0
        account.days_saved_count = 0
        account.is_savings_mature = False
        account.savings_start_date = None

    db.session.commit()

    for table, deleted in counts.items():
        print(f"  deleted {deleted:>3}  {table}")
    print(f"  reset       savings_account (balance=0, days=0, mature=False)"
          if account else "  (no savings account on file)")
    print(f"\nPreserved: profile, KYC, documents, stall assignment, login for {name}.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        sys.exit(__doc__)
    app = create_app()
    with app.app_context():
        reset(int(sys.argv[1]))
