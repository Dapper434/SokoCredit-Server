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