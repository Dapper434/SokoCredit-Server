"""Per-institution Daraja credential resolution + at-rest encryption.

Secrets (consumer key/secret, passkey) are stored Fernet-encrypted on the
LendingInstitution row. The Fernet key comes from the MPESA_ENC_KEY env var and
is only touched when M-Pesa credentials are read or written — the rest of the
app runs without it.
"""
import os
from dataclasses import dataclass
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

SANDBOX_BASE_URL = "https://sandbox.safaricom.co.ke"
PRODUCTION_BASE_URL = "https://api.safaricom.co.ke"


class MpesaConfigError(Exception):
    """M-Pesa is not usable for this request. Carries an HTTP-ish status code."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = os.environ.get("MPESA_ENC_KEY")
    if not key:
        raise MpesaConfigError(
            "MPESA_ENC_KEY is not set. Generate one with "
            '`python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"` and add it to .env.',
            status_code=500,
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise MpesaConfigError(f"MPESA_ENC_KEY is not a valid Fernet key: {exc}", 500)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a credential for storage. Returns urlsafe-base64 ciphertext."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise MpesaConfigError(
            "Stored M-Pesa credential could not be decrypted — MPESA_ENC_KEY may "
            "have changed since it was saved. Re-seed the credentials.",
            status_code=500,
        )


@dataclass(frozen=True)
class MpesaConfig:
    institution_id: int
    consumer_key: str
    consumer_secret: str
    passkey: str
    shortcode: str
    environment: str

    @property
    def base_url(self) -> str:
        return PRODUCTION_BASE_URL if self.environment == "production" else SANDBOX_BASE_URL


def resolve_config(institution_id: int) -> MpesaConfig:
    """Load and decrypt an institution's Daraja credentials.

    Raises MpesaConfigError (status 400) if the institution has no credentials —
    the caller should surface "M-Pesa is not configured for this institution."
    """
    from extensions import db
    from foundations.models import LendingInstitution

    inst = db.session.get(LendingInstitution, institution_id)
    if inst is None:
        raise MpesaConfigError(f"No such lending institution ({institution_id}).", 404)

    required = (
        inst.mpesa_consumer_key,
        inst.mpesa_consumer_secret,
        inst.mpesa_passkey,
        inst.mpesa_stk_shortcode,
    )
    if not all(required):
        raise MpesaConfigError(
            f"M-Pesa is not configured for {inst.registered_business_name}.",
            status_code=400,
        )

    return MpesaConfig(
        institution_id=institution_id,
        consumer_key=decrypt_secret(inst.mpesa_consumer_key),
        consumer_secret=decrypt_secret(inst.mpesa_consumer_secret),
        passkey=decrypt_secret(inst.mpesa_passkey),
        shortcode=inst.mpesa_stk_shortcode,
        environment=inst.mpesa_environment or "sandbox",
    )


def callback_base_url() -> str:
    """Public HTTPS base Safaricom will POST callbacks to (e.g. an ngrok URL).

    Falls back to the local server; the simulated-payload path (Phase 3C) does
    not need this to be publicly reachable.
    """
    return os.environ.get("MPESA_CALLBACK_BASE_URL", "http://localhost:5000").rstrip("/")
