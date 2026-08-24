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