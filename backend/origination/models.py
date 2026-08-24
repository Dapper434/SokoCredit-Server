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
    lat = db.Column(db.Numeric(9,6), nullable=True)
    lng = db.Column(db.Numeric(9,6), nullable=True)

    def __repr__(self):
        return f"<MarketStall {self.market_name} # {self.stall_number} "


class CustomerProfile(db.Model):
    #turns a person into a bankable customer record

    __tablename__ = "customer_profiles"
    __table_args__ = (
        db.CheckConstraint(
            f"credit_tier is NULL OR credit_tier IN {CREDIT_TIERS}", 
            name="ck_customer_credit_tier_valid"
        )
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
    badges = db.relationship("CustomerBadge", back_populates="customer_profiles", lazy="dynamic")

    def __repr__(self):
        return f"<CustomerProfile {self.id} nid={self.national_id_number}"

