from datetime import datetime, timezone
from extensions import db

def utcnow():
    return datetime.now(timezone.utc)

REPAYMENT_SCHEDULE_STATUSES = ("pending", "paid", "overdue", "partial")
CHANNELS = ("mpesa", "airtel_money", "bank_transfer", "cash")
TRANSACTION_TYPES = ("disbursement", "repayment", "penalty", "fee")
TRANSACTION_STATUSES = ("pending", "completed", "failed", "reversed")
RESCHEDULE_DECISIONS = ("pending", "approved", "rejected")
RESCHEDULE_MODES = ("extend_tenure", "grace_period")

class RepaymentSchedule(db.Model):
    __tablename__ = "repayment_schedules"
    __table_args__ = (
        db.CheckConstraint(f"status IN {REPAYMENT_SCHEDULE_STATUSES}", name="ck_rep_sched_status_valid"),
    )

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False, index=True)
    installment_number = db.Column(db.Integer, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    
    principal_due = db.Column(db.Numeric(14, 2), nullable=False)
    interest_due = db.Column(db.Numeric(14, 2), nullable=False)
    total_due = db.Column(db.Numeric(14, 2), nullable=False)
    
    amount_paid = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="pending")
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<RepaymentSchedule loan={self.loan_id} inst={self.installment_number} due={self.due_date}>"

class Transaction(db.Model):
    __tablename__ = "transactions"
    __table_args__ = (
        db.CheckConstraint(f"channel IN {CHANNELS}", name="ck_txn_channel_valid"),
        db.CheckConstraint(f"transaction_type IN {TRANSACTION_TYPES}", name="ck_txn_type_valid"),
        db.CheckConstraint(f"status IN {TRANSACTION_STATUSES}", name="ck_txn_status_valid"),
    )

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False, index=True)
    repayment_schedule_id = db.Column(db.Integer, db.ForeignKey("repayment_schedules.id"), nullable=True, index=True)
    
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    channel = db.Column(db.String(20), nullable=False)
    gateway_reference = db.Column(db.String(255), unique=True, nullable=True) # e.g. M-Pesa receipt number
    transaction_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="completed")
    allocation_breakdown = db.Column(db.JSON, nullable=True)

    # M-Pesa STK correlation. checkout_request_id is assigned when the STK push
    # is initiated; the receipt number lands in gateway_reference on callback.
    checkout_request_id = db.Column(db.String(80), unique=True, nullable=True, index=True)
    merchant_request_id = db.Column(db.String(80), nullable=True)
    failure_reason = db.Column(db.String(255), nullable=True)
    raw_callback = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self):
        return f"<Transaction loan={self.loan_id} amount={self.amount} type={self.transaction_type} status={self.status}>"

class RescheduleRequest(db.Model):
    __tablename__ = "reschedule_requests"
    __table_args__ = (
        db.CheckConstraint(f"admin_decision IN {RESCHEDULE_DECISIONS}", name="ck_resched_req_decision_valid"),
        db.CheckConstraint(f"requested_mode IN {RESCHEDULE_MODES}", name="ck_resched_req_mode_valid"),
    )

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False, index=True)
    requested_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    
    reason_category = db.Column(db.String(100), nullable=False)
    requested_mode = db.Column(db.String(50), nullable=False)
    requested_extension_days = db.Column(db.Integer, nullable=False)
    
    admin_decision = db.Column(db.String(20), nullable=False, default="pending")
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self):
        return f"<RescheduleRequest loan={self.loan_id} mode={self.requested_mode} decision={self.admin_decision}>"

class RepaymentScheduleHistory(db.Model):
    __tablename__ = "repayment_schedules_history"

    id = db.Column(db.Integer, primary_key=True)
    repayment_schedule_id = db.Column(db.Integer, db.ForeignKey("repayment_schedules.id"), nullable=False, index=True)
    reschedule_request_id = db.Column(db.Integer, db.ForeignKey("reschedule_requests.id"), nullable=False, index=True)
    archived_snapshot = db.Column(db.JSON, nullable=False)
    archived_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self):
        return f"<RepaymentScheduleHistory sched={self.repayment_schedule_id} resched={self.reschedule_request_id}>"
