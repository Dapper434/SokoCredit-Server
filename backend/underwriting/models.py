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


class Loan(db.Model):
    __tablename__ = "loans"
    __table_args__ = (
        db.CheckConstraint(f"status IN {LOAN_STATUSES}", name="ck_loans_status_valid"),
        db.CheckConstraint(
            f"repayment_frequency IN {REPAYMENT_FREQUENCIES}", name="ck_loans_repayment_frequency_valid"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    lending_institution_id = db.Column(
        db.Integer, db.ForeignKey("lending_institutions.id"), nullable=False, index=True
    )
    customer_profile_id = db.Column(
        db.Integer, db.ForeignKey("customer_profiles.id"), nullable=False, index=True
    )

    principal = db.Column(db.Numeric(14, 2), nullable=False)
    interest_rate = db.Column(db.Numeric(6, 4), nullable=False)
    term_days = db.Column(db.Integer, nullable=False)
    repayment_frequency = db.Column(db.String(20), nullable=False)
    loan_purpose = db.Column(db.String(255), nullable=True)

    status = db.Column(db.String(20), nullable=False, default="pending")

    disbursed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    maturity_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    approvals = db.relationship("LoanApproval", back_populates="loan", lazy="dynamic")

    def __repr__ (self):
        return f"<Loan {self.id} customer={self.customer_profile_id} status={self.status}>"


class LoanApproval(db.Model):
    __tablename__ = "loan_approvals"
    __table_args__ = (
        db.CheckConstraint(f"decision IN {APPROVAL_DECISIONS}", name="ck_loan_approvals_decision_valid"),
    )

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False, index=True)
    maker_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    checker_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    maker_notes = db.Column(db.Text, nullable=True)
    checker_notes = db.Column(db.Text, nullable=True)

    decision = db.Column(db.String(20), nullable=False, default="pending")
    maker_action_at = db.Column(db.DateTime(timezone=True),default=utcnow, nullable=False)
    checker_action_at = db.Column(db.DateTime(timezone=True), nullable=True)

    loan = db.relationship("Loan", back_populates="approvals")

    def __repr__(self):
        return f"<LoanApproval loan={self.loan_id} decision={self.decision}>"


class CreditScoreLog(db.Model):
    #one row per tier recalculation
    #underwriting writes here after every recalculation
    #pushes the new tier to Origination

    __tablename__ = "credit_score_log"

    id = db.Column(db.Integer, primary_key=True)
    customer_profile_id = db.Column(
        db.Integer, db.ForeignKey("customer_profiles.id"), nullable=False,index=True
    )

    previous_tier = db.Column(db.String(10), nullable=True)
    new_tier = db.Column(db.String(10), nullable=False)
    score_components = db.Column(db.JSON, nullable=True)
    calculated_at = db.Column(db.DateTime(timezone=True), default=utcnow,nullable=False)

    def __repr__(self):
        return f"<CreditScoreLog customer={self.customer_profile_id} tier={self.new_tier}>"