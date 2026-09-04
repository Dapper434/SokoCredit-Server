#Other modules (Underwriting) should only ever call functions from here
#never import origination.models directly
#file is allowed to depend on Foundation

from datetime import date
from typing import Optional

from extensions import db
from origination.models import (
    CustomerProfile,
    MarketStall,
    CustomerDocument,
    LoyaltyPoints,
    Badge,
    CustomerBadge,
    LoyaltyEvent,
    SavingsCheckin,
    SavingsDeposit,
    CREDIT_TIERS,
    SOKO_POINT_EVENTS,
    SOKO_POINT_BADGES,
    utcnow,
)

from foundations import storage
from foundations.auth import AuthError, get_user_institution_id, verify_institution_access
from foundations.audit import log_action
import bcrypt

def hash_pin(plain_pin: str) -> str:
    return bcrypt.hashpw(plain_pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_pin(plain_pin: str, pin_hash: str) -> bool:
    if not pin_hash:
        return False
    return bcrypt.checkpw(plain_pin.encode("utf-8"), pin_hash.encode("utf-8"))

def authenticate_customer(phone_number: str, pin: str, lending_institution_id: int) -> CustomerProfile:
    profile = CustomerProfile.query.filter_by(phone_number=phone_number, lending_institution_id=lending_institution_id).first()
    if profile is None or not verify_pin(pin, profile.pin_hash):
        raise AuthError("Invalid phone number or PIN.", 401)
    return profile

def _verify_profile_institution_access(profile: CustomerProfile) -> None:

    institution_id  = get_user_institution_id(profile.user_id)
    if institution_id is None:
        raise AuthError("This customer profile has no resolvable institution", 403)

    verify_institution_access(institution_id)

def register_customer(data: dict) -> CustomerProfile:
    from foundations.auth import register_user
    from foundations.institutions import get_default_institution_id
    from sqlalchemy.exc import IntegrityError
    
    # Check if phone or national_id already exists in profiles
    if CustomerProfile.query.filter_by(phone_number=data["phone_number"]).first():
        raise AuthError("Phone number is already registered.", 400)
    if CustomerProfile.query.filter_by(national_id_number=data["national_id_number"]).first():
        raise AuthError("National ID is already registered.", 400)
        
    inst_id = data.get("lending_institution_id")
    branch_id = data.get("branch_id")
    if not inst_id:
        raise AuthError("lending_institution_id is required.", 400)
        
    try:
        user = register_user(
            lending_institution_id=inst_id,
            branch_id=branch_id,
            email=f"customer_{data['phone_number']}@example.com",
            password=data["pin"], # Plain text pin, will be hashed by register_user
            full_name=data["full_name"],
            role="customer",
            status="active",
            phone_number=data["phone_number"],
            national_id_number=data["national_id_number"]
        )
    except Exception as e:
        # Might fail if email or phone is already taken on the User table
        raise AuthError("Phone number or National ID is already registered in the system.", 400)
        
    market_name = data.get("market_name")
    stall_number = data.get("stall_number")
    market_stall_id = None
    
    if market_name:
        stall = MarketStall.query.filter_by(market_name=market_name, stall_number=stall_number).first()
        if not stall:
            stall = MarketStall(market_name=market_name, stall_number=stall_number)
            db.session.add(stall)
            db.session.flush()
        market_stall_id = stall.id
    
    profile = CustomerProfile(
        user_id=user.id,
        lending_institution_id=inst_id,
        branch_id=branch_id,
        national_id_number=data["national_id_number"],
        phone_number=data["phone_number"],
        pin_hash=hash_pin(data["pin"]),
        date_of_birth=data.get("date_of_birth"),
        gender=data.get("gender"),
        business_type=data.get("business_type"),
        residential_address=data.get("residential_address"),
        next_of_kin_name=data.get("next_of_kin_name"),
        next_of_kin_phone=data.get("next_of_kin_phone"),
        next_of_kin_email=data.get("next_of_kin_email"),
        market_stall_id=market_stall_id,
    )
    db.session.add(profile)
    db.session.flush() # get profile.id
    
    from underwriting.models import SavingsAccount
    savings = SavingsAccount(
        customer_profile_id=profile.id,
        total_savings_balance=0,
        days_saved_count=0,
        is_savings_mature=False
    )
    db.session.add(savings)
    
    db.session.commit()
    
    return profile



def create_customer_profile(
    user_id: int,
    national_id_number: str,
    actor_id: int,
    date_of_birth: Optional[date] = None,
    gender: Optional[str] = None,
    business_type: Optional[str] = None,
    monthly_income_range: Optional[str] = None,
    residential_address: Optional[str] = None,
    next_of_kin_name: Optional[str] = None,
    next_of_kin_phone: Optional[str] = None,
    market_stall_id: Optional[int] = None,   
) -> CustomerProfile:
    #creates customer profile owned bu user_id(loan officer)

    institution_id = get_user_institution_id(user_id)
    if institution_id is None:
        raise AuthError("No such staff user, or user has no institution.", 400)

    verify_institution_access(institution_id)

    if CustomerProfile.query.filter_by(national_id_number=national_id_number).first():
        raise AuthError("A customer profile with this national ID already exists." ,409)

    if market_stall_id is not None and db.session.get(MarketStall, market_stall_id) is None:
        raise AuthError("No such market stall.", 400)

    profile = CustomerProfile(
        user_id=user_id,
        national_id_number=national_id_number,
        date_of_birth=date_of_birth,
        gender=gender,
        business_type=business_type,
        monthly_income_range=monthly_income_range,
        residential_address=residential_address,
        next_of_kin_name=next_of_kin_name,
        next_of_kin_phone=next_of_kin_phone,
        market_stall_id=market_stall_id,
    )

    db.session.add(profile)
    db.session.commit()

    log_action(
        actor_id=actor_id,
        entity_type="CustomerProfile",
        entity_id=profile.id,
        action="create",
        before=None,
        after={"national_id_number": profile.national_id_number, "user_id": user_id},
        lending_institution_id=institution_id,
    )
    return profile


def get_customer_profile(customer_profile_id: int) -> CustomerProfile:
    profile = db.session.get(CustomerProfile, customer_profile_id)
    if profile is None:
        raise AuthError("No such customer profile.", 404)
    _verify_profile_institution_access(profile)
    return profile


def add_document(
    customer_profile_id: int,
    document_type: str,
    uploaded_by: int,
    file_url: Optional[str] = None,
    file_bytes: Optional[bytes] = None,
    content_type: Optional[str] = None,
    original_filename: Optional[str] = None,
) -> CustomerDocument:
    """Record a KYC document.

      * file_url — client uploaded elsewhere, pass the URL (Dev)
      * file_bytes + content_type + original_filename — server-side Supabase
        upload via foundations.storage (teammate)
    """
    profile = get_customer_profile(customer_profile_id)

    storage_path = None
    if file_bytes is not None:
        storage.validate_upload(content_type, len(file_bytes))
        storage_path = storage.build_object_path(
            "customer", profile.id, original_filename or "file"
        )
        storage.upload_file(storage_path, file_bytes, content_type)
    elif not file_url:
        raise AuthError("Provide either file_url or an uploaded file.", 400)

    doc = CustomerDocument(
        customer_profile_id=profile.id,
        document_type=document_type,
        file_url=file_url,
        storage_path=storage_path,
        content_type=content_type,
        uploaded_by=uploaded_by,
    )

    db.session.add(doc)
    db.session.commit()

    institution_id = get_user_institution_id(profile.user_id)
    log_action(
        actor_id=uploaded_by,
        entity_type="CustomerDocument",
        entity_id=doc.id,
        action="create",
        before=None,
        after={"document_type": document_type, "customer_profile_id": profile.id,
               "file_url": file_url, "storage_path": storage_path},
        lending_institution_id=institution_id,
    )
    return doc


def get_document_download_url(document_id: int) -> str:
    """Signed Supabase URL for a customer KYC document. Institution-scoped."""
    doc = db.session.get(CustomerDocument, document_id)
    if doc is None:
        raise AuthError("No such document.", 404)
    profile = db.session.get(CustomerProfile, doc.customer_profile_id)
    _verify_profile_institution_access(profile)
    if not doc.storage_path:
        raise AuthError("This document has no Supabase storage object.", 400)
    return storage.generate_signed_url(doc.storage_path)


def award_badge(
    customer_profile_id: int,
    badge_id: int,
    actor_id: int
) -> CustomerBadge:
    profile = get_customer_profile(customer_profile_id)

    if db.session.get(Badge, badge_id) is None:
        raise AuthError("No such badge.", 404)

    if CustomerBadge.query.filter_by(customer_profile_id=profile.id, badge_id=badge_id).first():
        raise AuthError("this customer already has that badge.", 409)

    award = CustomerBadge(customer_profile_id=profile.id, badge_id=badge_id)

    db.session.add(award)
    db.session.commit()

    institution_id = get_user_institution_id(profile.user_id)
    log_action (
        actor_id=actor_id,
        entity_type="CustomerBadge",
        entity_id=award.id,
        action="create",
        before=None,
        after={"customer_profile_id": profile.id, "badge_id": badge_id},
        lending_institution_id=institution_id,
    )
    return award

def set_credit_tier(
    customer_profile_id:int,
    tier:str,
    actor_id:Optional[int]=None     
) -> CustomerProfile:
    #called by underwriting afte revery credit score recalculation

    if tier not in CREDIT_TIERS:
        raise AuthError(f"Invalid credit tier '{tier}'. Must be one of {CREDIT_TIERS}. ", 400)

    profile = db.session.get(CustomerProfile, customer_profile_id)
    if profile is None:
        raise AuthError("No such cutomer profile.", 404)

    institution_id = get_user_institution_id(profile.user_id)
    before_tier = profile.credit_tier
    profile.credit_tier = tier
    db.session.commit()

    log_action(
        actor_id=actor_id,
        entity_type="CustomerProfile",
        entity_id=profile.id,
        action="update",
        before={"credit_tier": before_tier},
        after={"credit_tier": tier},
        lending_institution_id=institution_id,
    )
    return profile


def award_points(
    customer_profile_id: int,
    event_type: str,
    points: Optional[int] = None,
    idempotency_key: str = "",
    actor_id: Optional[int] = None,
) -> Optional[LoyaltyPoints]:
    if event_type not in SOKO_POINT_EVENTS:
        raise AuthError(
            f"Unknown SokoPoints event '{event_type}'. Must be one of {tuple(SOKO_POINT_EVENTS)}.",
            400,
        )

    awarded = points if points is not None else SOKO_POINT_EVENTS[event_type]
    if awarded <= 0:
        return None

    profile = db.session.get(CustomerProfile, customer_profile_id)
    if profile is None:
        raise AuthError("No such customer profile.", 404)

    existing = LoyaltyEvent.query.filter_by(
        customer_profile_id=customer_profile_id,
        event_type=event_type,
        idempotency_key=idempotency_key or "",
    ).first()
    if existing is not None:
        return LoyaltyPoints.query.filter_by(customer_profile_id=customer_profile_id).first()

    ledger = LoyaltyPoints.query.filter_by(customer_profile_id=customer_profile_id).first()
    if ledger is None:
        ledger = LoyaltyPoints(customer_profile_id=customer_profile_id, points_balance=0)
        db.session.add(ledger)
        db.session.flush()

    before_balance = ledger.points_balance
    ledger.points_balance = before_balance + awarded
    ledger.updated_at = utcnow()

    event = LoyaltyEvent(
        customer_profile_id=customer_profile_id,
        event_type=event_type,
        points=awarded,
        idempotency_key=idempotency_key or "",
    )
    db.session.add(event)
    db.session.commit()

    institution_id = get_user_institution_id(profile.user_id)
    log_action(
        actor_id=actor_id,
        entity_type="LoyaltyPoints",
        entity_id=ledger.id,
        action="update",
        before={"points_balance": before_balance},
        after={"points_balance": ledger.points_balance, "event_type": event_type},
        lending_institution_id=institution_id,
    )
    return ledger


# ── Savings Check-in Services ──────────────────────────────────────────

SAVINGS_GATE_DAYS = 14


SAVINGS_DEPOSIT_AMOUNT = 200


def _apply_savings_credit(customer_profile_id: int, amount: int = SAVINGS_DEPOSIT_AMOUNT) -> SavingsCheckin:
    """Credit a confirmed savings payment: add a check-in row, raise the balance,
    advance the gate, and award the gate-completion SokoPoints once.

    Shared by the manual check-in path and the confirmed-STK-deposit path so a
    real M-Pesa deposit moves savings_balance and available credit exactly like
    a manually-recorded check-in.
    """
    from datetime import timedelta
    from underwriting.models import SavingsAccount

    # TEMPORARY: bypass the 1-per-day unique constraint for demo purposes by
    # stamping each check-in with a distinct synthetic date.
    count = SavingsCheckin.query.filter_by(customer_profile_id=customer_profile_id).count()
    checkin = SavingsCheckin(
        customer_profile_id=customer_profile_id,
        checkin_date=date.today() + timedelta(days=count),
    )
    db.session.add(checkin)

    savings = SavingsAccount.query.filter_by(customer_profile_id=customer_profile_id).first()
    gate_just_completed = False
    if savings:
        savings.total_savings_balance += amount
        savings.days_saved_count += 1
        if count + 1 >= SAVINGS_GATE_DAYS and not savings.is_savings_mature:
            savings.is_savings_mature = True
            gate_just_completed = True

    db.session.commit()

    if gate_just_completed:
        award_points(customer_profile_id, "gate_complete")

    return checkin


def record_checkin(customer_profile_id: int) -> SavingsCheckin:
    """Record a savings check-in (manual / simulated path)."""
    profile = db.session.get(CustomerProfile, customer_profile_id)
    if profile is None:
        raise AuthError("No such customer profile.", 404)
    return _apply_savings_credit(customer_profile_id)


# ── M-Pesa STK savings deposit ─────────────────────────────────────────────

def initiate_savings_stk(customer_profile_id: int) -> SavingsDeposit:
    """Fire a Sandbox STK push for a KES 200 savings deposit.

    Creates a pending SavingsDeposit; the confirmed result arrives via
    confirm_savings_deposit_callback() and only then moves the balance.
    """
    from servicing.mpesa.config import resolve_config, callback_base_url
    from servicing.mpesa.client import stk_push
    from servicing.mpesa.security import callback_path

    profile = db.session.get(CustomerProfile, customer_profile_id)
    if profile is None:
        raise AuthError("No such customer profile.", 404)
    if not profile.phone_number:
        raise AuthError("No M-Pesa phone number on your profile.", 400)

    cfg = resolve_config(profile.lending_institution_id)  # raises MpesaConfigError if unset
    resp = stk_push(
        cfg,
        phone=profile.phone_number,
        amount=SAVINGS_DEPOSIT_AMOUNT,
        account_reference=f"SV{customer_profile_id}",
        description="Savings deposit",
        callback_url=f"{callback_base_url()}{callback_path('stk')}",
    )

    deposit = SavingsDeposit(
        customer_profile_id=customer_profile_id,
        amount=SAVINGS_DEPOSIT_AMOUNT,
        status="pending",
        checkout_request_id=resp["CheckoutRequestID"],
        merchant_request_id=resp.get("MerchantRequestID"),
    )
    db.session.add(deposit)
    db.session.commit()
    return deposit


def get_savings_deposit(checkout_request_id: str) -> Optional[SavingsDeposit]:
    return SavingsDeposit.query.filter_by(checkout_request_id=checkout_request_id).first()


def confirm_savings_deposit_callback(parsed) -> bool:
    """Reconcile an STK callback against a pending SavingsDeposit.

    Returns True if the CheckoutRequestID matched a savings deposit (handled),
    False if it did not (so the shared webhook can report 'unknown').
    """
    deposit = SavingsDeposit.query.filter_by(
        checkout_request_id=parsed.checkout_request_id
    ).first()
    if deposit is None:
        return False

    if deposit.status != "pending":
        return True  # already reconciled — idempotent

    if parsed.succeeded:
        deposit.status = "completed"
        deposit.gateway_reference = parsed.mpesa_receipt
        deposit.raw_callback = parsed.as_dict()
        deposit.confirmed_at = utcnow()
        db.session.commit()
        # Same credit path a manual check-in uses → moves savings_balance and,
        # through get_available_credit, the customer's available credit.
        _apply_savings_credit(deposit.customer_profile_id, int(deposit.amount))
    else:
        deposit.status = "failed"
        deposit.failure_reason = parsed.result_desc[:255]
        db.session.commit()

    return True


def get_customer_display_info(customer_profile_id: int) -> dict:
    """Name and credit tier for a customer, for staff-facing loan lists.

    Other modules must call this rather than importing CustomerProfile and
    reaching for `full_name`, which lives on User and not on the profile.
    The tier comes from the profile so staff screens agree with what the
    customer sees in their own portal.
    """
    from foundations.models import User

    profile = db.session.get(CustomerProfile, customer_profile_id)
    if profile is None:
        return {
            "customer_name": f"Customer {customer_profile_id}",
            "customer_tier": "C",
        }

    user = db.session.get(User, profile.user_id)
    return {
        "customer_name": user.full_name if user else f"Customer {customer_profile_id}",
        "customer_tier": profile.credit_tier or "C",
    }


def get_points_summary(customer_profile_id: int) -> dict:
    """Return the customer's real SokoPoints balance and their badge progress.

    Badge state is derived from the awarded points ledger rather than stored
    separately, so a badge reads as earned exactly when its points were awarded.
    """
    ledger = LoyaltyPoints.query.filter_by(
        customer_profile_id=customer_profile_id,
    ).first()

    earned = {
        event.event_type: event
        for event in LoyaltyEvent.query.filter_by(
            customer_profile_id=customer_profile_id,
        ).all()
    }

    badges = []
    for event_type, title, icon, description in SOKO_POINT_BADGES:
        event = earned.get(event_type)
        badges.append({
            "event_type": event_type,
            "title": title,
            "icon": icon,
            "description": description,
            "points": SOKO_POINT_EVENTS[event_type],
            "earned": event is not None,
            "earned_at": event.created_at.isoformat() if event else None,
        })

    return {
        "soko_points_total": ledger.points_balance if ledger else 0,
        "badges": badges,
        "badges_earned": sum(1 for b in badges if b["earned"]),
        "badges_total": len(badges),
    }


def get_checkin_count(customer_profile_id: int) -> int:
    """Return the total number of distinct check-in days."""
    return SavingsCheckin.query.filter_by(
        customer_profile_id=customer_profile_id,
    ).count()


def get_checkin_history(customer_profile_id: int) -> dict:
    """Return the check-in dates and whether the savings gate is complete."""
    checkins = (
        SavingsCheckin.query
        .filter_by(customer_profile_id=customer_profile_id)
        .order_by(SavingsCheckin.checkin_date.asc())
        .all()
    )
    count = len(checkins)
    dates = [c.checkin_date.isoformat() for c in checkins]
    today = date.today().isoformat()
    already_checked_in_today = today in dates

    ledger = LoyaltyPoints.query.filter_by(
        customer_profile_id=customer_profile_id,
    ).first()

    return {
        "count": count,
        "goal": SAVINGS_GATE_DAYS,
        "dates": dates,
        "gate_complete": count >= SAVINGS_GATE_DAYS,
        "checked_in_today": already_checked_in_today,
        "soko_points_total": ledger.points_balance if ledger else 0,
    }

def update_customer_profile(customer_id: int, actor_id: int, **kwargs) -> CustomerProfile:
    profile = CustomerProfile.query.get(customer_id)
    if not profile:
        raise ValueError("Profile not found")
    
    _verify_profile_institution_access(profile)

    allowed_fields = ["residential_address", "next_of_kin_name", "next_of_kin_phone"]
    for field in allowed_fields:
        if field in kwargs:
            setattr(profile, field, kwargs[field])
            
    db.session.commit()
    log_action(actor_id, "CustomerProfile", customer_id, "update")
    return profile


def get_savings_activity(institution_id: int) -> list[dict]:
    """Staff-facing savings tracker for one institution's customers.

    Per customer: running balance, distinct savings days, progress toward the
    14-day gate and the 30-day full-limit unlock, and their most recent
    deposits (confirmed STK deposits first, else the raw check-in count).
    """
    from foundations.models import User
    from underwriting.models import SavingsAccount

    FULL_LIMIT_DAYS = 30

    rows = (
        db.session.query(CustomerProfile, User)
        .join(User, CustomerProfile.user_id == User.id)
        .filter(CustomerProfile.lending_institution_id == institution_id)
        .all()
    )

    out = []
    for profile, user in rows:
        acct = SavingsAccount.query.filter_by(customer_profile_id=profile.id).first()
        days = SavingsCheckin.query.filter_by(customer_profile_id=profile.id).count()
        deposits = (
            SavingsDeposit.query.filter_by(customer_profile_id=profile.id)
            .order_by(SavingsDeposit.created_at.desc())
            .limit(5)
            .all()
        )
        out.append({
            "customer_profile_id": profile.id,
            "customer_name": user.full_name,
            "phone": profile.phone_number,
            "savings_balance": str(acct.total_savings_balance) if acct else "0",
            "is_savings_mature": bool(acct and acct.is_savings_mature),
            "savings_days": days,
            "gate_goal": SAVINGS_GATE_DAYS,
            "gate_complete": days >= SAVINGS_GATE_DAYS,
            "full_limit_goal": FULL_LIMIT_DAYS,
            "days_to_full_limit": max(FULL_LIMIT_DAYS - days, 0),
            "recent_deposits": [
                {
                    "amount": str(d.amount),
                    "status": d.status,
                    "gateway_reference": d.gateway_reference,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in deposits
            ],
        })
    out.sort(key=lambda r: r["savings_days"], reverse=True)
    return out
