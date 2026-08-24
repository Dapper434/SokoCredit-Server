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

"""replace organization model with lending institution model"""

class LendingInstitution(db.Model):
   __tablename__ = "lending_institutions"
   __table_args__ = (
       db.CheckConstraint(f"status IN {INSTITUTION_STATUSES}", name="ck_institutions_status_valid"),
   )

   id = db.Column(db.Integer, primary_key=True)

   #Business identity & physical prescence -> page 1
   registered_business_name = db.Column(db.String(255), nullable=False)
   registration_number = db.Column(db.String(100), unique=True, nullable=False)
   #BRS reg / cert no
   kra_pin = db.Column(db.String(50), unique=True, nullable=False)
   operating_liscence_type = db.Column(db.String(100), nullable=False)
   cbk_liscence_number = db.Column(db.String(100), unique=True, nullable=False)
   head_office_address = db.Column(db.String(255), nullable=False)
   head_office_lat = db.Column(db.Numeric(9,6), nullable=True)
   head_office_long = db.Column(db.Numeric(9,6), nullable=True)

   #Regulatory compliance & operation footprint -> page 2
   county_business_permit_number = db.Column(db.String(255), unique=True, nullable=False)
   odpc_registration_number = db.Column(db.String(100), nullable=True)
   estimated_staff_count = db.Column(db.Integer, nullable=True)

   #operational settlement -> page 3
   bank_name = db.Column(db.String(255), nullable=False)
   bank_account_number = db.Column(db.String(100), unique=True, nullable=False)
   collection_paybill_number = db.Column(db.String(20), nullable=False)
   default_interest_rate = db.Column(db.Numeric(6,4), nullable=False)
   default_penalty_rate = db.Column(db.Numeric(6,4), nullable=False)
   status = db.Column(db.String(20), nullable=False, default="pending_review")
   created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

   users = db.relationship("User", back_populates="lending_institution", lazy="dynamic")
   documents = db.relationship("InstitutionDocument", back_populates="lending_institution", lazy="dynamic")
   markets = db.relationship("InstitutionMarket", back_populates="lending_institution", lazy="dynamic")

   def __repr__(self):
       return f"<LendingInstitution {self.id} {self.registered_business_name}>"


class User(db.Model):
    #Lender staff - loan officers, managers, admins, super_admins

    __tablename__ = "users"
    __table_args__ = (
        db.CheckConstraint(f"role IN {ROLES}", name="ck_users_role_valid"),
        db.CheckConstraint(f"status IN {USER_STATUSES}", name="ck_users_status_valid"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lending_institution_id = db.Column(
        db.Integer, db.ForeignKey("lending_institutions.id"), nullable=False, index=True
    )

    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=True)
    national_id_number = db.Column(db.String(20), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="loan_officer")
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)

    lending_institution = db.relationship("LendingInstitution", back_populates="users")

    def __repr__(self):
        return f"<User {self.id} {self.email} institution={self.lending_institution_id}>"


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer,primary_key=True)
    lending_institution_id = db.Column(
        db.Integer, db.ForeignKey("lending_institutions.id"), nullable=False, index=True
    )
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)

    entity_type = db.Column(db.String(100), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    action = db.Column(db.String(100), nullable=False)

    before = db.Column(db.JSON, nullable=True)
    after = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<AuditLog {self.entity_type} #{self.entity_id} {self.action}>"


class InstitutionDocument(db.Model):
    #compliance document uploads captured during onboarding
    #stores metadata - file_url points & storage location

    __tablename__ = "institution_documents"

    id = db.Column(db.Integer, primary_key=True)
    lending_institution_id = db.Column(
        db.Integer, db.ForeignKey("lending_institutions.id"), nullable=False, index=True
    )
    document_type = db.Column(db.String(50), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    uploaded_at = db.column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    lending_institution = db.relationship("LendingInstitution", back_populates="documents")

    def __repr__(self):
        return f"<InstitutionDocument {self.document_type} inst={self.lending_institution_id}>"


class InstitutionMarket(db.Model):
    #markets an institution operates in

    __tablename__ = "institution_markets"

    id = db.Column(db.Integer, primary_key=True)
    lending_institution_id = db.Column(
        db.Integer, db.ForeignKey("lending_institutions.id"), nullable=False, index=True
    )
    market_name = db.Column(db.String(150), nullable=False)

    lending_institution = db.relationship("LendingInstitution", back_populates="markets")

    def __repr__(self):
        return f"<InstitutionMarket {self.market_name} inst={self.lending_institution_id}>"