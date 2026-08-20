from datetime import datetime, timezone

from extensions import db

#ROLES tuple of allowed roles to be reused across the app for RBAC
ROLES = ("loan_officer", "manager", "admin", "super_admin")

#freshy called every time a row is inserted
def utcnow():
    return datetime.now(timezone.utc)

class Organisation(db.Model):
    __tablename__ = "organizations"
 
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)

    #unique slug for the organization, used in URLs and for identification
    slug = db.Column(db.String(150), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    #one to many relationship with users, back_populates to allow for bidirectional access
    users = db.relationship("User", back_populates="organization", lazy="dynamic")
 
    def __repr__(self):
        return f"<Organization {self.id} {self.slug}>"