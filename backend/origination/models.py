from datetime import datetime, timezone
from extensions import db


#credit tier written by Underwriting module
CREDIT_TIERS = ("A","B","C")

def utcnow():
    return datetime.now(timezone.utc)

class MarketStall(db.Model):
    #physical market stall location

    __tablename__ = "market_stalls"

    id = db.Column(db.Integer, primary_key=True)
    market_name = db.Column(db.String(150), nullable=False)
    stall_number = db.Column(db.String(50), nullable=True)
    county = db.Column(db.String(100), nullable=True)
    lat = db.Column(db.Numeric(9, 6), nullable=True)
    lng = db.Column(db.Numeric(9, 6), nullable=True)

    def __repr__(self):
        return f"<MarketStall {self.market_name} # {self.stall_number}>"


class CustomerProfile(db.Model):
    #turns a person into a bankable customer record

    __tablename__ = "customer_profiles"
    __table_args__ = (
        db.CheckConstraint(
            f"credit_tier is NULL OR credit_tier IN {CREDIT_TIERS}", 
            name="ck_customer_credit_tier_valid"
        ),
        db.UniqueConstraint("lending_institution_id", "national_id_number", name="uq_customer_institution_nid"),
        db.UniqueConstraint("lending_institution_id", "phone_number", name="uq_customer_institution_phone"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lending_institution_id = db.Column(
        db.Integer, db.ForeignKey("lending_institutions.id"), nullable=False, index=True
    )
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    national_id_number = db.Column(db.String(20), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    business_type = db.Column(db.String(100), nullable=True)
    monthly_income_range = db.Column(db.String(50), nullable=True)
    residential_address = db.Column(db.String(255), nullable=True)
    next_of_kin_name = db.Column(db.String(150), nullable=True)
    next_of_kin_phone = db.Column(db.String(20), nullable=True)
    next_of_kin_email = db.Column(db.String(150), nullable=True)

    # Customer Authentication
    phone_number = db.Column(db.String(20), nullable=True, index=True)
    pin_hash = db.Column(db.String(255), nullable=True)

    market_stall_id = db.Column(db.Integer, db.ForeignKey("market_stalls.id"), nullable=True, index=True)

    credit_tier = db.Column(db.String(1), nullable = True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    market_stall = db.relationship("MarketStall")

    documents = db.relationship("CustomerDocument", back_populates="customer_profile", lazy="dynamic")
    loyalty_points = db.relationship("LoyaltyPoints", back_populates="customer_profile", uselist=False)
    badges = db.relationship("CustomerBadge", back_populates="customer_profile", lazy="dynamic")

    def __repr__(self):
        return f"<CustomerProfile {self.id} nid={self.national_id_number}>"


class CustomerDocument(db.Model):
    #KYC document uploads

    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    customer_profile_id = db.Column(
        db.Integer, db.ForeignKey("customer_profiles.id"), nullable=False, index=True
    )
    document_type = db.Column(db.String(50), nullable=False)
    # file_url: client-supplied URL (Dev).  storage_path + content_type:
    # server-side Supabase upload (teammate). Either strategy is valid.
    file_url = db.Column(db.String(500), nullable=True)
    storage_path = db.Column(db.String(500), nullable=True)
    content_type = db.Column(db.String(100), nullable=True)

    uploaded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    customer_profile = db.relationship("CustomerProfile", back_populates="documents")

    def __repr__(self):
        return f"<CustomerDocument {self.document_type} profile={self.customer_profile_id}>"

class LoyaltyPoints(db.Model):
    #one to one with customer profiles
    __tablename__ = "loyalty_points"

    id = db.Column(db.Integer, primary_key=True)
    customer_profile_id = db.Column(
        db.Integer, db.ForeignKey("customer_profiles.id"), unique=True, nullable=False, index=True
    )

    points_balance = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    customer_profile = db.relationship("CustomerProfile", back_populates = "loyalty_points")

    def __repr__(self):
        return f"<LoyaltyPoints profile={self.customer_profile_id} balance={self.points_balance}>"

class Badge(db.Model):
    #a badge definition

    __tablename__ = "badges"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    icon = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<Badge {self.title}>"

SOKO_POINT_EVENTS = {
    "gate_complete": 50,
    "loan_repaid_on_time": 100,
    "tier_upgrade": 70,
    "savings_streak": 200,
    "five_loans_zero_defaults": 100,
}

# Presentation for each earnable achievement. Keyed by the SOKO_POINT_EVENTS
# event that earns it, so a badge is shown as earned exactly when its points
# have been awarded — the two can never disagree. Ordered as displayed.
SOKO_POINT_BADGES = (
    ("gate_complete", "Savings Starter", "🌱", "Completed the 14-day savings gate."),
    ("loan_repaid_on_time", "On-Time Payer", "⚡", "Repaid a loan on or before its due date."),
    ("tier_upgrade", "Tier Climber", "📈", "Advanced to a higher credit tier."),
    ("savings_streak", "30-Day Streak", "📅", "Saved for 30 consecutive days."),
    ("five_loans_zero_defaults", "Clean Record", "🏆", "Completed 5 loans with zero defaults."),
)


class LoyaltyEvent(db.Model):
    # idempotency ledger for SokoPoints awards
    __tablename__ = "loyalty_events"
    __table_args__ = (
        db.UniqueConstraint(
            "customer_profile_id",
            "event_type",
            "idempotency_key",
            name="uq_loyalty_event_once",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    customer_profile_id = db.Column(
        db.Integer, db.ForeignKey("customer_profiles.id"), nullable=False, index=True
    )
    event_type = db.Column(db.String(50), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    idempotency_key = db.Column(db.String(100), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self):
        return f"<LoyaltyEvent profile={self.customer_profile_id} {self.event_type}>"


class CustomerBadge(db.Model):
    #join table for customers and badges

    __tablename__ = "customer_badges"
    __table_args__ = (
        db.UniqueConstraint("customer_profile_id", "badge_id", name="uq_customer_badge_once"),
    )

    id = db.Column(db.Integer, primary_key=True)
    customer_profile_id = db.Column(
        db.Integer, db.ForeignKey("customer_profiles.id"), nullable=False, index=True
    )
    badge_id = db.Column(db.Integer, db.ForeignKey("badges.id"), nullable=False, index=True)
    earned_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    customer_profile = db.relationship("CustomerProfile", back_populates="badges")

    badge = db.relationship("Badge")

    def __repr__(self):
        return f"<CustomerBadge profile={self.customer_profile_id} badge={self.badge_id}>"


class SavingsCheckin(db.Model):
    """Daily savings check-in for the 14-day savings gate.
    A customer must complete 14 check-ins before becoming eligible for a loan."""

    __tablename__ = "savings_checkins"
    __table_args__ = (
        db.UniqueConstraint(
            "customer_profile_id", "checkin_date",
            name="uq_savings_checkin_per_day",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    customer_profile_id = db.Column(
        db.Integer, db.ForeignKey("customer_profiles.id"), nullable=False, index=True
    )
    checkin_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self):
        return f"<SavingsCheckin profile={self.customer_profile_id} date={self.checkin_date}>"

SAVINGS_DEPOSIT_STATUSES = ("pending", "completed", "failed")


class SavingsDeposit(db.Model):
    """An M-Pesa STK savings deposit, from initiation to confirmed result.

    Distinct from SavingsCheckin: this tracks the *payment*, which starts
    'pending' at STK initiation and is reconciled when Safaricom's callback
    arrives. A confirmed deposit is what increments the savings balance and
    (for the first 14) records a SavingsCheckin.
    """

    __tablename__ = "savings_deposits"
    __table_args__ = (
        db.CheckConstraint(
            f"status IN {SAVINGS_DEPOSIT_STATUSES}", name="ck_savings_deposit_status_valid"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    customer_profile_id = db.Column(
        db.Integer, db.ForeignKey("customer_profiles.id"), nullable=False, index=True
    )
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")

    checkout_request_id = db.Column(db.String(80), unique=True, nullable=True, index=True)
    merchant_request_id = db.Column(db.String(80), nullable=True)
    gateway_reference = db.Column(db.String(255), nullable=True)  # M-Pesa receipt number
    failure_reason = db.Column(db.String(255), nullable=True)
    raw_callback = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    confirmed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<SavingsDeposit profile={self.customer_profile_id} amount={self.amount} status={self.status}>"
