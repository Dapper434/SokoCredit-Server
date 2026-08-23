#handles institutions onboarding and compliance workflow

from typing import Optional

from extensions import db
from foundations.models import LendingInstitution, InstitutionDocument, InstitutionMarket, User
from foundations.auth import AuthError, register_user
from foundations.audit import log_action

MAX_MARKETS_PER_INSTITUTION = 6

def register_instistution(
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

    log_action(
        actor_id=admin.id,
        entity_type="LendingInstitution",
        entity_id=institution.id,
        action="create",
        before=None,
        after={"registration_number": registration_number, "status":"pending_review"},
        lending_institution=institution.id,
    )

    #auto approve for now
    #approve_institution(institution.id,actor=None)

    db.session.refresh(institution)
    db.session.refresh(admin)
    return institution, admin

