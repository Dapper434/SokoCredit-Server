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
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    national_id_number = db.Column(db.String(20), unique=True, nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    business_type = db.Column(db.String(100), nullable=True)
    monthly_income_range = db.Column(db.String(50), nullable=True)
    residential_address = db.Column(db.String(255), nullable=True)
    next_of_kin_name = db.Column(db.String(150), nullable=True)
    next_of_kin_phone = db.Column(db.String(20), nullable=True)

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
    storage_path = db.Column(db.String(500), nullable=False)
    content_type = db.Column(db.String(100), nullable=False)

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