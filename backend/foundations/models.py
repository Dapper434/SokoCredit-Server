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


class User(db.Model):
    __tablename__ = "users"

    #enforce table level guard rail
    __table_args__ = (
        db.CheckConstraint(f"role IN {ROLES}", name="ck_users_role_valid"),
    )
    
    id = db.Column(db.Integer, primary_key=True)

    #makes sure you cant create a user pointing to an organisation that doesnt exist, and also makes sure you cant delete an organisation that has users 
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
 
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="loan_officer")
 
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)

    #one to many relationship with organizations, back_populates to allow for bidirectional access
    organization = db.relationship("Organization", back_populates="users")
 
    def __repr__(self):
        return f"<User {self.id} {self.email} org={self.organization_id}>"