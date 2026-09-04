"""
ROLES:
password hashing, creating users/ orgs
loggin in, enforcing permissions, and
issuing tokens
"""

from datetime import datetime, timezone
from functools import wraps
from typing import Optional
import re

import bcrypt
from flask import jsonify
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    current_user,
)

from extensions import db
from foundations.models import User, ROLES, LendingInstitution
from foundations.audit import log_action

"""
Define a custom exception for authentication errors
To be used in routes.py
"""
class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

# password hashing
def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


#register new user, and log the action in the audit log
def register_user(
    lending_institution_id: int,
    email:str,
    password:str,
    full_name:str,
    role:str = "loan_officer",
    actor_id: Optional[int] = None,
    status: str = "active",
    phone_number: Optional[str] = None,
    national_id_number: Optional[str] = None,
    branch_id: Optional[int] = None,
    is_founding_admin: bool = False,
) -> User:
    #creates a user under an existing institution
    if role not in ROLES:
     raise AuthError(f"Invalid role '{role}'. Must be one of {ROLES}.", 400)

    email = email.lower().strip()

    if role in ("branch_manager", "loan_officer") and not is_founding_admin:
        inst = db.session.get(LendingInstitution, lending_institution_id)
        if not inst:
            raise AuthError("Invalid institution.", 400)
            
        pattern = r"^(?P<first>[a-z]+)\.(?P<last>[a-z]+)@(?P<subdomain>bm|lo)\.(?P<root_domain>[a-z0-9.-]+\.[a-z]{2,})$"
        match = re.match(pattern, email)
        if not match:
            raise AuthError("Invalid staff email format. Expected format: first.last@{bm|lo}.domain", 400)
            
        expected_subdomain = "bm" if role == "branch_manager" else "lo"
        if match.group("subdomain") != expected_subdomain:
            raise AuthError(f"Email subdomain does not match role. Expected '{expected_subdomain}'.", 400)
            
        if match.group("root_domain") != inst.domain:
            raise AuthError(f"Email domain must match institution domain '{inst.domain}'.", 400)

    if User.query.filter_by(lending_institution_id=lending_institution_id, email=email).first():
        raise AuthError ("A user with this email already exists in this institution.", 409)

    user = User(
        lending_institution_id=lending_institution_id,
        branch_id=branch_id,
        email=email,
        phone_number=phone_number,
        national_id_number=national_id_number,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
        status=status,
    )

    db.session.add(user)
    db.session.commit()

    log_action(
        actor_id=actor_id if actor_id is not None else user.id,
        entity_type="User",
        entity_id=user.id,
        action="create",
        before=None,
        after={
            "email": user.email,
            "role": user.role,
            "lending_institution_id":lending_institution_id,
        },
        lending_institution_id=lending_institution_id,
    )
    return user

#authenticate user and update last_login_at
def authenticate_user(email: str, password: str) -> User:
    user = User.query.filter_by(email=email.lower().strip()).first()
    
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("Invalid email or password.", 401)
        
    if user.lending_institution_id is None:
        raise AuthError("Invalid email or password.", 401)
        
    if user.status.lower() != "active":
        raise AuthError("Invalid email or password.", 401)
        
    if not user.lending_institution or user.lending_institution.status.lower() != "active":
        raise AuthError("Invalid email or password.", 401)
 
    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()
    return user

#issue tokens
def issue_tokens(user: User) -> dict:
    claims = {
        "lending_institution_id": user.lending_institution_id, 
        "branch_id": user.branch_id,
        "role": user.role
    }
    return {
        "access_token": create_access_token(identity=str(user.id), additional_claims=claims),
        "refresh_token": create_refresh_token(identity=str(user.id), additional_claims=claims),
    }

#JWT wirings, to get the current user from the token and to check if the user is active
def register_jwt_callbacks(jwt_manager) -> None:
    # define a user lookup callback to load the user from the database using the identity in the JWT
    @jwt_manager.user_lookup_loader
    def load_user_from_token(_jwt_header, jwt_data):
        user_id = jwt_data["sub"]
        return db.session.get(User, int(user_id))

    # define a user loader callback to check if the user is active before allowing access to protected routes
    @jwt_manager.expired_token_loader
    def expired_token(_jwt_header, _jwt_data):
        return jsonify({"error": "Token has expired."}), 401

    @jwt_manager.invalid_token_loader
    def invalid_token(reason):
        return jsonify({"error": f"Invalid token: {reason}"}), 401
 
    @jwt_manager.unauthorized_loader
    def missing_token(reason):
        return jsonify({"error": f"Missing token: {reason}"}), 401
    
def get_current_user() -> User:
    return current_user

"""
permissions dictionary maps each role to a set of 
permission strings its allowed to do
"""
PERMISSIONS = {
    "loan_officer": {"customer:create", "loan:create", "repayment:record"},
    "branch_manager": {"*"},  # everything, including cross-module admin actions
}


def role_required(*allowed_roles: str):
    #Simple permissions checks, ie are they in the named roles
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            if claims.get("role") not in allowed_roles:
                return jsonify({"error": "Insufficient role for this action."}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator

""" 
Restricts routes to a specific permission string
Allows simple change of permissions by simply adding them to the permissions dictionary
"""
def permission_required(permission: str):

    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            role = claims.get("role")
            granted = PERMISSIONS.get(role, set())
            if "*" not in granted and permission not in granted:
                return jsonify({"error": f"Missing permission: {permission}"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def verify_institution_access(resource_lending_institution_id: int) -> None:
    claims = get_jwt()
    if claims.get("lending_institution_id") != resource_lending_institution_id:
        raise AuthError("This resource does not belong to your organization.", 403)

def get_user_institution_id(user_id:int) -> Optional[int]:
    #lets other modules resolve which institution a staff belongs to
    #without importing foundations.models.User directly
    user = db.session.get(User, user_id)
    return user.lending_institution_id if user else None

def get_user_contact_info(user_id: int) -> Optional[dict]:
    # lets other modules (Collections/Communications) resolve a staff member's
    # contact details without importing foundations.models.User directly
    user = db.session.get(User, user_id)
    if user is None:
        return None
    return {"email": user.email, "phone_number": user.phone_number}
