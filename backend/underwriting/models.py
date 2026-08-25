from datetime import datetime, timezone
from extensions import db

LOAN_STATUSES = ("pending","active","restructured","fully_paid","defaulted")
REPAYMENT_FREQUENCIES = ("daily", "weekly", "lump_sum")
CREDIT_TIERS = ("A","B","C")

APPROVAL_DECISIONS = ("pending", "approved", "rejected")

def utcnow():
    return datetime.now(timezone.utc)

class SavingsAccount(db.Model):
    #one savings account per customer
    
    __tablename__ = "savings_accounts"

    id = db.Column(db.Integer, primary_key=True)

    #one-to-one with Origination's customer_profiles

    customer_profile_id = db.Column(
        db.Integer, db.ForeignKey("customer_profiles.id"), nullable=False, unique=True,
        index=True
    )
    total_savings_balance = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    days_saved_count = db.Column(db.Integer, nullable=False, default=0)
    savings_start_date = db.Column(db.Date, nullable=True)
    is_savings_mature = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"<SavingsAccount customer={self.customer_profile_id} mature={self.is_savings_mature}>"