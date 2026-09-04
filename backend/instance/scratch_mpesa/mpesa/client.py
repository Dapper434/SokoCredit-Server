"""Thin Daraja Sandbox client: OAuth token cache + STK push.

No B2C — disbursement stays an internal book entry (out of scope). No Flask or
business-logic imports here; this module only talks HTTP to Safaricom.
"""
import base64
import os
import time
import uuid
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from servicing.mpesa.config import MpesaConfig, MpesaConfigError

_TIMEOUT = (5, 20)  # (connect, read) seconds
_token_cache: dict[str, tuple[str, float]] = {}  # consumer_key -> (token, expires_at)


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def normalize_phone(msisdn: str) -> str:
    """Return a Safaricom MSISDN as 2547XXXXXXXX / 2541XXXXXXXX."""
    digits = "".join(ch for ch in str(msisdn) if ch.isdigit())
    if digits.startswith("254"):
        return digits
    if digits.startswith("0"):
        return "254" + digits[1:]
    if digits.startswith("7") or digits.startswith("1"):
        return "254" + digits
    return digits


def _access_token(cfg: MpesaConfig) -> str:
    cached = _token_cache.get(cfg.consumer_key)
    if cached and cached[1] > time.time() + 30:
        return cached[0]

    resp = _session().get(
        f"{cfg.base_url}/oauth/v1/generate?grant_type=client_credentials",
        auth=(cfg.consumer_key, cfg.consumer_secret),
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        raise MpesaConfigError(
            f"Daraja OAuth failed ({resp.status_code}): {resp.text[:200]}", 502
        )
    data = resp.json()
    token = data["access_token"]
    expires_in = int(data.get("expires_in", 3599))
    _token_cache[cfg.consumer_key] = (token, time.time() + expires_in)
    return token


def _password(cfg: MpesaConfig, timestamp: str) -> str:
    raw = f"{cfg.shortcode}{cfg.passkey}{timestamp}".encode()
    return base64.b64encode(raw).decode()


def stk_push(
    cfg: MpesaConfig,
    *,
    phone: str,
    amount,
    account_reference: str,
    description: str,
    callback_url: str,
) -> dict:
    """Fire an STK push. Returns the Daraja response dict.

    On success it carries MerchantRequestID, CheckoutRequestID, ResponseCode
    ("0" means accepted for processing — the real result comes by callback).
    """
    # Demo insurance (Phase 3C): with no real Daraja app credentials and/or no
    # public callback URL, skip the network call and return a well-formed
    # acceptance. The pending record is still created; the result is then driven
    # in via POST /api/servicing/webhooks/mpesa/simulate.
    if os.environ.get("MPESA_SANDBOX_STUB") == "1":
        crid = f"ws_CO_{datetime.now().strftime('%d%m%Y%H%M%S')}{uuid.uuid4().hex[:6]}"
        return {
            "MerchantRequestID": f"sim-{uuid.uuid4().hex[:12]}",
            "CheckoutRequestID": crid,
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing (STUB).",
            "CustomerMessage": "Success. Request accepted for processing (STUB).",
        }

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    payload = {
        "BusinessShortCode": cfg.shortcode,
        "Password": _password(cfg, timestamp),
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(round(float(amount))),  # Daraja Sandbox wants whole KES
        "PartyA": normalize_phone(phone),
        "PartyB": cfg.shortcode,
        "PhoneNumber": normalize_phone(phone),
        "CallBackURL": callback_url,
        "AccountReference": account_reference[:12],
        "TransactionDesc": description[:20],
    }
    resp = _session().post(
        f"{cfg.base_url}/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers={"Authorization": f"Bearer {_access_token(cfg)}"},
        timeout=_TIMEOUT,
    )
    try:
        data = resp.json()
    except ValueError:
        raise MpesaConfigError(f"Daraja STK returned non-JSON ({resp.status_code}).", 502)

    if resp.status_code != 200 or str(data.get("ResponseCode", "")) != "0":
        msg = data.get("errorMessage") or data.get("ResponseDescription") or resp.text[:200]
        raise MpesaConfigError(f"STK push rejected by Daraja: {msg}", 502)
    return data
