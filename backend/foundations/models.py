from datetime import datetime, timezone

from extensions import db

#ROLES tuple of allowed roles to be reused across the app for RBAC
ROLES = ("loan_officer", "manager", "admin", "super_admin")
#institution status for onboarding institutions by system owners
INSTITUTION_STATUSES=("pending_review","active","suspended")
#individual staff statuses updated by institution admins
USER_STATUSES=("pending","active","suspended")

#freshy called every time a row is inserted
def utcnow():
    return datetime.now(timezone.utc)


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

class AuditLog(db.Model):
    __tablename__ = "audit_logs"
 
    id = db.Column(db.Integer, primary_key=True)
    #each audit log is associated with an organization
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )

    #is nullable as an action can be system created
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    """ 
    generic pointers to any row in any table
    allows log_action() to be reuseable across every module
    """
    entity_type = db.Column(db.String(100), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)

    #traces the action performed on the entity, and the state of the entity before and after the action
    action = db.Column(db.String(20), nullable=False)

    #before and after state of the entity
    #create: before -> null , after -> new entity
    #update: before -> old entity, after -> new entity
    #delete: before -> old entity, after -> null
    before = db.Column(db.JSON, nullable=True)
    after = db.Column(db.JSON, nullable=True)
 
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)
 
    def __repr__(self):
        return f"<AuditLog {self.entity_type}#{self.entity_id} {self.action}>"