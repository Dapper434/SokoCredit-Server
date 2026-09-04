from datetime import datetime, timezone

from extensions import db

#ROLES tuple of allowed roles to be reused across the app for RBAC
ROLES = ("loan_officer", "branch_manager", "customer")
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
   code = db.Column(db.String(50), unique=True, nullable=False)
   domain = db.Column(db.String(100), unique=True, nullable=False)
   #BRS reg / cert no
   kra_pin = db.Column(db.String(50), unique=True, nullable=False)
   operating_license_type = db.Column(db.String(100), nullable=True)
   cbk_license_number = db.Column(db.String(100), unique=True, nullable=True)
   head_office_address = db.Column(db.String(255), nullable=False)
   head_office_lat = db.Column(db.Numeric(9,6), nullable=True)
   head_office_lng = db.Column(db.Numeric(9,6), nullable=True)

   #Regulatory compliance & operation footprint -> page 2
   county_business_permit_number = db.Column(db.String(255), nullable=True)
   odpc_registration_number = db.Column(db.String(100), nullable=True)
   estimated_staff_count = db.Column(db.Integer, nullable=True)

   #operational settlement -> page 3
   bank_name = db.Column(db.String(255), nullable=True)
   bank_account_number = db.Column(db.String(100), nullable=True)
   collection_paybill_number = db.Column(db.String(20), nullable=True)
   airtel_paybill_number = db.Column(db.String(20), nullable=True)
   default_interest_rate = db.Column(db.Numeric(6,4), nullable=True)
   default_penalty_rate = db.Column(db.Numeric(6,4), nullable=True)

   # M-Pesa Daraja credentials, per institution. The three secret values are
   # Fernet-encrypted at rest (see servicing.mpesa.config); shortcode and
   # environment are not sensitive. Unset for an institution => M-Pesa not
   # configured, and STK there fails with a clear message rather than crashing.
   mpesa_consumer_key = db.Column(db.Text, nullable=True)
   mpesa_consumer_secret = db.Column(db.Text, nullable=True)
   mpesa_passkey = db.Column(db.Text, nullable=True)
   mpesa_stk_shortcode = db.Column(db.String(20), nullable=True)
   mpesa_environment = db.Column(db.String(20), nullable=True)  # 'sandbox' | 'production'

   # Institution's own ceiling on a single customer's available credit.
   # Nullable for schema symmetry, but every institution MUST be seeded — an
   # unset value is treated as a hard error, never a silent global default.
   max_loan_limit = db.Column(db.Numeric(14,2), nullable=True)
   status = db.Column(db.String(20), nullable=False, default="pending_review")
   created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

   users = db.relationship("User", back_populates="lending_institution", lazy="dynamic")
   documents = db.relationship("InstitutionDocument", back_populates="lending_institution", lazy="dynamic")
   markets = db.relationship("InstitutionMarket", back_populates="lending_institution", lazy="dynamic")
   branches = db.relationship("Branch", back_populates="lending_institution", lazy="dynamic")

   def __repr__(self):
       return f"<LendingInstitution {self.id} {self.registered_business_name}>"


class Branch(db.Model):
    # Physical branches for lending institutions
    
    __tablename__ = "branches"
    
    id = db.Column(db.Integer, primary_key=True)
    lending_institution_id = db.Column(
        db.Integer, db.ForeignKey("lending_institutions.id"), nullable=False, index=True
    )
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), nullable=False)
    
    lending_institution = db.relationship("LendingInstitution", back_populates="branches")
    users = db.relationship("User", back_populates="branch", lazy="dynamic")
    
    __table_args__ = (
        db.UniqueConstraint("lending_institution_id", "code", name="uq_branch_institution_code"),
    )
    
    def __repr__(self):
        return f"<Branch {self.code} inst={self.lending_institution_id}>"


class User(db.Model):
    #Lender staff - loan officers, branch managers

    __tablename__ = "user"
    __table_args__ = (
        db.CheckConstraint(f"role IN {ROLES}", name="ck_users_role_valid"),
        db.CheckConstraint(f"status IN {USER_STATUSES}", name="ck_users_status_valid"),
        db.UniqueConstraint("lending_institution_id", "email", name="uq_user_institution_email"),
        db.UniqueConstraint("lending_institution_id", "phone_number", name="uq_user_institution_phone"),
        db.UniqueConstraint("lending_institution_id", "national_id_number", name="uq_user_institution_nid"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lending_institution_id = db.Column(
        db.Integer, db.ForeignKey("lending_institutions.id"), nullable=False, index=True
    )
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True, index=True)

    email = db.Column(db.String(255), nullable=False, index=True)
    phone_number = db.Column(db.String(20), nullable=True)
    national_id_number = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="loan_officer")
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)

    lending_institution = db.relationship("LendingInstitution", back_populates="users")
    branch = db.relationship("Branch", back_populates="users")

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
    # Two supported storage strategies (merge of Dev + teammate work):
    #  - file_url: client uploaded elsewhere, stored the URL string (Dev)
    #  - storage_path + content_type: server-side Supabase upload (teammate)
    file_url = db.Column(db.String(500), nullable=True)
    storage_path = db.Column(db.String(500), nullable=True)
    content_type = db.Column(db.String(100), nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

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
    

SETTING_REQUEST_STATUSES = ("pending", "approved", "rejected")
SETTLEMENT_FIELDS = (
    "bank_name",
    "bank_account_number",
    "collection_paybill_number",
    "default_interest_rate",
    "default_penalty_rate",
    "max_loan_limit",
)


class InstitutionSettingRequest(db.Model):
    # Four-Eyes change requests for settlement / rate fields

    __tablename__ = "institution_setting_requests"
    __table_args__ = (
        db.CheckConstraint(
            f"status IN {SETTING_REQUEST_STATUSES}",
            name="ck_inst_setting_req_status_valid",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    lending_institution_id = db.Column(
        db.Integer, db.ForeignKey("lending_institutions.id"), nullable=False, index=True
    )
    requested_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    field_changed = db.Column(db.String(100), nullable=False)
    old_value = db.Column(db.String(255), nullable=True)
    new_value = db.Column(db.String(255), nullable=False)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self):
        return f"<InstitutionSettingRequest {self.id} {self.field_changed} {self.status}>"