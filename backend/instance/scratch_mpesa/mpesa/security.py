"""Internal auth for webhook routes.

Webhook routes deliberately skip @jwt_required() (Safaricom can't carry a JWT).
Instead the callback URL we hand Daraja carries a shared secret token, and we
optionally also check the source IP against Safaricom's published ranges.

This is the "internal auth mechanism" the architecture doc flagged as needed
for background/webhook writes.
"""
import ipaddress
import os

from flask import request

# Safaricom publishes these as the origin ranges for Daraja callbacks.
_SAFARICOM_CIDRS = [
    "196.201.214.0/24",
    "196.201.215.0/24",
    "196.201.212.0/24",
    "196.201.213.0/24",
    "196.201.176.0/24",
]


class WebhookAuthError(Exception):
    def __init__(self, message: str = "Webhook authentication failed."):
        super().__init__(message)
        self.message = message
        self.status_code = 401


def webhook_token() -> str:
    """Shared secret embedded in the callback URL. Dev default is fine for Sandbox."""
    return os.environ.get("MPESA_WEBHOOK_TOKEN", "soko-sandbox-webhook")


def callback_path(kind: str) -> str:
    """Path (incl. token) to give Daraja as CallBackURL for `kind` in {'stk'}."""
    return f"/api/servicing/webhooks/mpesa/{kind}/{webhook_token()}"


def _ip_allowed(remote_addr: str) -> bool:
    if os.environ.get("MPESA_TRUST_ALL_WEBHOOK_IPS", "1") == "1":
        return True  # dev default: tunnels/localhost aren't Safaricom IPs
    try:
        ip = ipaddress.ip_address(remote_addr)
    except ValueError:
        return False
    return any(ip in ipaddress.ip_network(c) for c in _SAFARICOM_CIDRS)


def verify_webhook(token_from_path: str) -> None:
    """Raise WebhookAuthError unless the request is an authentic Daraja callback."""
    if token_from_path != webhook_token():
        raise WebhookAuthError("Invalid webhook token.")
    if not _ip_allowed(request.remote_addr or ""):
        raise WebhookAuthError("Source IP not in the Safaricom allowlist.")
