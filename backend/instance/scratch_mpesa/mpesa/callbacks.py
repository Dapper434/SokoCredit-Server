"""Parse + validate incoming Safaricom STK callback payloads.

Real Daraja STK callback shape:
{
  "Body": {"stkCallback": {
     "MerchantRequestID": "...", "CheckoutRequestID": "...",
     "ResultCode": 0, "ResultDesc": "The service request is processed successfully.",
     "CallbackMetadata": {"Item": [
        {"Name": "Amount", "Value": 200.0},
        {"Name": "MpesaReceiptNumber", "Value": "QGH7..."},
        {"Name": "TransactionDate", "Value": 20260904153000},
        {"Name": "PhoneNumber", "Value": 254708374149}]}}}
}
On failure (e.g. user cancelled) ResultCode != 0 and CallbackMetadata is absent.
"""
import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


class CallbackParseError(Exception):
    pass


@dataclass(frozen=True)
class ParsedCallback:
    merchant_request_id: str
    checkout_request_id: str
    result_code: int
    result_desc: str
    amount: Optional[Decimal] = None
    mpesa_receipt: Optional[str] = None
    phone_number: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.result_code == 0

    def as_dict(self) -> dict:
        """JSON-safe dict for storing in a JSON column (Decimal -> str)."""
        return {
            "merchant_request_id": self.merchant_request_id,
            "checkout_request_id": self.checkout_request_id,
            "result_code": self.result_code,
            "result_desc": self.result_desc,
            "amount": str(self.amount) if self.amount is not None else None,
            "mpesa_receipt": self.mpesa_receipt,
            "phone_number": self.phone_number,
        }


def parse_stk_callback(body: dict) -> ParsedCallback:
    if not isinstance(body, dict):
        raise CallbackParseError("Callback body is not an object.")

    stk = (body.get("Body") or {}).get("stkCallback")
    if not isinstance(stk, dict):
        raise CallbackParseError("Missing Body.stkCallback.")

    crid = stk.get("CheckoutRequestID")
    if not crid:
        raise CallbackParseError("Missing CheckoutRequestID.")

    try:
        result_code = int(stk.get("ResultCode"))
    except (TypeError, ValueError):
        raise CallbackParseError("Missing or non-integer ResultCode.")

    meta_items = ((stk.get("CallbackMetadata") or {}).get("Item")) or []
    meta = {i.get("Name"): i.get("Value") for i in meta_items if isinstance(i, dict)}

    amount = meta.get("Amount")
    return ParsedCallback(
        merchant_request_id=stk.get("MerchantRequestID", ""),
        checkout_request_id=crid,
        result_code=result_code,
        result_desc=stk.get("ResultDesc", ""),
        amount=Decimal(str(amount)) if amount is not None else None,
        mpesa_receipt=meta.get("MpesaReceiptNumber"),
        phone_number=str(meta["PhoneNumber"]) if meta.get("PhoneNumber") is not None else None,
    )


def build_simulated_callback(
    *,
    merchant_request_id: str,
    checkout_request_id: str,
    result_code: int = 0,
    amount=None,
    mpesa_receipt: Optional[str] = None,
    phone_number: str = "254708374149",
) -> dict:
    # A real M-Pesa receipt is unique per payment; keep the simulated one unique
    # too so it never collides with transactions.gateway_reference.
    if mpesa_receipt is None:
        mpesa_receipt = "SIM" + secrets.token_hex(4).upper()
    """A realistic Daraja STK callback body, for the Phase 3C fallback path."""
    stk = {
        "MerchantRequestID": merchant_request_id or "sim-merchant",
        "CheckoutRequestID": checkout_request_id,
        "ResultCode": result_code,
        "ResultDesc": (
            "The service request is processed successfully."
            if result_code == 0
            else "Request cancelled by user."
        ),
    }
    if result_code == 0:
        stk["CallbackMetadata"] = {
            "Item": [
                {"Name": "Amount", "Value": float(amount if amount is not None else 0)},
                {"Name": "MpesaReceiptNumber", "Value": mpesa_receipt},
                {"Name": "PhoneNumber", "Value": int(phone_number)},
            ]
        }
    return {"Body": {"stkCallback": stk}}
