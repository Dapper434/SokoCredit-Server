#handles institutions onboarding and compliance workflow

from typing import Optional

from sqlalchemy.exc import IntegrityError
from extensions import db
from foundations.models import LendingInstitution, InstitutionDocument, InstitutionMarket, User
from foundations.auth import AuthError, register_user
from foundations.audit import log_action

MAX_MARKETS_PER_INSTITUTION = 6

def register_institution(
    registered_business_name: str,
    registration_number: str,
    kra_pin: str,
    head_office_address:str,
    admin_email:str,
    admin_password:str,
    admin_full_name: str,
    admin_national_id_number: Optional[str] = None,
    operating_license_type: Optional[str] = None,
    cbk_license_number: Optional[str] = None,
    county_business_permit_number: Optional[str] = None,
    odpc_registration_number: Optional[str] = None,
    estimated_staff_count: Optional[int] = None,
    head_office_lat: Optional[float] = None,
    head_office_lng: Optional[float] = None,
    bank_name: Optional[str] = None,
    bank_account_number: Optional[str] = None,
    collection_paybill_number: Optional[str] = None,
    default_interest_rate: Optional[float] = None,
    default_penalty_rate: Optional[float] = None,
) -> tuple[LendingInstitution, User]:
    #Onboards an brand new lending institution plus its founding admin
    #institutions are auto approved for now 

    if LendingInstitution.query.filter_by(registration_number=registration_number).first():
        raise AuthError("A lending institution with this registration number already exists.", 409)

    if LendingInstitution.query.filter_by(kra_pin=kra_pin).first():
        raise AuthError("An institution with this KRA PIN already exists.", 409)

    institution = LendingInstitution(
        registered_business_name=registered_business_name,
        registration_number=registration_number,
        kra_pin=kra_pin,
        operating_license_type=operating_license_type,
        cbk_license_number=cbk_license_number,
        county_business_permit_number=county_business_permit_number,
        odpc_registration_number=odpc_registration_number,
        estimated_staff_count=estimated_staff_count,
        head_office_address=head_office_address,
        head_office_lat=head_office_lat,
        head_office_lng=head_office_lng,
        bank_name=bank_name,
        bank_account_number=bank_account_number,
        collection_paybill_number=collection_paybill_number,
        default_interest_rate=default_interest_rate,
        default_penalty_rate=default_penalty_rate,
        status="pending_review",
    )
    try:
        db.session.add(institution)
        db.session.flush() #assign institution.id without commiting

        admin = register_user(
            lending_institution_id=institution.id,
            email=admin_email,
            password=admin_password,
            full_name=admin_full_name,
            role="super_admin",
            national_id_number=admin_national_id_number,
        )
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        error_msg = str(e).lower()
        if "cbk_license_number" in error_msg:
            raise AuthError("An institution with this CBK license number already exists.", 409)
        if "email" in error_msg:
            raise AuthError("A user with this email address is already registered.", 409)
        raise AuthError("Registration failed: an account with these details already exists.", 409)

    log_action(
        actor_id=admin.id,
        entity_type="LendingInstitution",
        entity_id=institution.id,
        action="create",
        before=None,
        after={"registration_number": registration_number, "status":"pending_review"},
        lending_institution_id=institution.id,
    )

    #auto approve for now
    approve_institution(institution.id,actor_id=None)

    db.session.refresh(institution)
    db.session.refresh(admin)
    return institution, admin

def attach_document(
    lending_institution_id: int,
    document_type:str,
    file_url: str,
    uploaded_by: int,
) -> InstitutionDocument:
    #records metadata for compliance documents upload

    institution = db.session.get(LendingInstitution, lending_institution_id)
    if institution is None:
        raise AuthError("No such institution", 404)

    doc = InstitutionDocument(
        lending_institution = lending_institution_id,
        document_type=document_type,
        file_url=file_url,
        uploaded_by=uploaded_by,
    )
    db.session.add(doc)
    db.session.commit()

    log_action(
        actor_id=uploaded_by,
        entity_type="InstitutionDocument",
        entity_id=doc.id,
        action="create",
        before=None,
        after={"document_type": document_type, "file_url": file_url},
        lending_institution_id=lending_institution_id,
    )

    return doc


def add_market(
    lending_institution_id:str,
    market_name:str,
    actor_id:int
) -> InstitutionMarket:
    #adds institution's operaing markets
    existing_count = InstitutionMarket.query.filter_by(
        lending_institution_id=lending_institution_id
    ).count()
    if existing_count >= MAX_MARKETS_PER_INSTITUTION:
        raise AuthError(f"An institution may list only {MAX_MARKETS_PER_INSTITUTION} markets.", 400)

    market = InstitutionMarket(
        lending_institution_id=lending_institution_id,
        market_name=market_name,
    )
    db.session.add(market)
    db.session.commit()

    log_action(
        actor_id = actor_id,
        entity_type="InstitutionMarket",
        entity_id=market.id,
        action="create",
        before=None,
        after={"market_name":market_name},
        lending_institution_id=lending_institution_id
    )
    return market

def submit_for_compliance_review(
     lending_institution_id:int,
     actor_id:int,
    ) -> LendingInstitution:

    institution = db.session.get(LendingInstitution, lending_institution_id)
    if institution is None:
        raise AuthError("No such institution", 404)

    log_action(
        actor_id=actor_id,
        entity_type="LendingInstitution",
        entity_id=institution.id,
        action="update",
        before={"status": institution.status},
        after={"status": institution.status, "submitted_for_review":True},
        lending_institution=institution.id,
    )
    return institution


def approve_institution(
    lending_institution_id:int,
    actor_id:Optional[int]=None,
) -> LendingInstitution:
    #flips institution from pending to active

    institution = db.session.get(LendingInstitution, lending_institution_id)
    if institution is None:
        raise AuthError("No such institution", 404)

    before_status = institution.status
    institution.status = "active"

    before_status = institution.status
    institution.status = "active"
    
    pending_admins = User.query.filter_by(
        lending_institution_id = lending_institution_id, status="pending"      
    ).all()

    for admin in pending_admins:
        admin.status = "active"

    db.session.commit()

    log_action(
        actor_id=actor_id,
        entity_type="LendingInstitution",
        entity_id=institution.id,
        action="update",
        before={"status": before_status},
        after={"status": "active"},
        lending_institution_id=institution.id,
    )
    return institution

"""
 To remove approve institution auto call:
  -> Remove auto call from inside register institution
  -> Expose this function behind a route restricted to a platform admin
     in foundation.routes.py that passes the reviewer's real actor_id
"""

    




