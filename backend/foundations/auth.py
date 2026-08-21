"""
ROLES:
password hashing, creating users/ orgs
loggin in, enforcing permissions, and
issuing tokens
"""

from datetime import datetime, timezone
from functools import wraps
from typing import Optional

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
from foundations.models import Organization, User, ROLES
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
    # parameters for the register_user function, which will create a new user in the database and log the action in the audit log

    organization_id: int,
    email: str,
    password: str,
    full_name: str,
    role: str = "loan_officer",
    actor_id: Optional[int] = None,
) -> User:
    
    # validate role from ROLES tuple
    if role not in ROLES:
        raise AuthError(f"Invalid role '{role}'. Must be one of {ROLES}.", 400)

    # check if user with email already exists in the organization, if so raise an error
    if User.query.filter_by(email=email.lower().strip()).first():
        raise AuthError("A user with this email already exists.", 409)

    # create the user and commit to the database
    user = User(
        organization_id=organization_id,
        email=email.lower().strip(),
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
    )
    db.session.add(user)
    db.session.commit()

    # log the action in the audit log, using the actor_id if provided, otherwise using the newly created user's id
    log_action(
        actor_id=actor_id if actor_id is not None else user.id,
        entity_type="User",
        entity_id=user.id,
        action="create",
        #action is create thus before is None, after is the snapshot of the user after creation
        before=None, 
        after={"email": user.email, "role": user.role, "organization_id": organization_id},
        organization_id=organization_id,
    )
    return user

#admin registers their new lending institution
def register_organization(
    name: str,
    slug: str,
    admin_email: str,
    admin_password: str,
    admin_full_name: str,
) -> tuple[Organization, User]:
    # only place where organisation id gets created
    if Organization.query.filter_by(slug=slug).first():
        raise AuthError("An organization with this slug already exists.", 409)
 
    org = Organization(name=name, slug=slug)
    db.session.add(org)
    db.session.flush()

    """
    assigns org.id without committing yet
    gives us a working organisation id but also ensures we can 
    roll back incase something goes worng
    """
    
    admin = register_user(
        organization_id=org.id,
        email=admin_email,
        password=admin_password,
        full_name=admin_full_name,
        role="admin",
    )
    db.session.commit()
    return org, admin

#authenticate user and update last_login_at
def authenticate_user(email: str, password: str) -> User:
    user = User.query.filter_by(email=email.lower().strip()).first()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        # Deliberately identical error for "no such user" and "wrong password"
        # so login responses can't be used to enumerate registered emails.
        raise AuthError("Invalid email or password.", 401)
 
    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()
    return user

#issue tokens
def issue_tokens(user: User) -> dict:
    claims = {"organization_id": user.organization_id, "role": user.role}
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