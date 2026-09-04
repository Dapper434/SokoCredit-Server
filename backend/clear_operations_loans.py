"""Clear the loan data shown in the Lender portal's Operations docket.

Operations shows loans with status active / overdue (Due/Overdue Queue) and
fully_paid (Live Collections). This deletes those loans and their dependent
rows (approvals, repayment schedules, transactions, reschedule requests).

pending applications on the Approval Desk and rejected loans are left alone.

Usage:  .venv/bin/python clear_operations_loans.py
"""
from app import create_app
from extensions import db
from underwriting.models import Loan, LoanApproval
from servicing.models import RepaymentSchedule, Transaction

OPERATIONS_STATUSES = ("active", "overdue", "fully_paid")

app = create_app()
with app.app_context():
    loans = Loan.query.filter(Loan.status.in_(OPERATIONS_STATUSES)).all()
    if not loans:
        print("Operations docket already empty — nothing to clear.")
    else:
        try:
            from servicing.models import RescheduleRequest
        except ImportError:
            RescheduleRequest = None

        for loan in loans:
            print(f"  removing loan #{loan.id}  profile={loan.customer_profile_id}  "
                  f"KES {loan.principal}  status={loan.status}")
            Transaction.query.filter_by(loan_id=loan.id).delete()
            RepaymentSchedule.query.filter_by(loan_id=loan.id).delete()
            LoanApproval.query.filter_by(loan_id=loan.id).delete()
            if RescheduleRequest is not None:
                RescheduleRequest.query.filter_by(loan_id=loan.id).delete()
            db.session.delete(loan)
        db.session.commit()
        print(f"\nCleared {len(loans)} loan(s) from Operations.")

    remaining = Loan.query.order_by(Loan.id).all()
    print("Remaining loans:",
          [(l.id, l.customer_profile_id, str(l.principal), l.status) for l in remaining] or "none")
