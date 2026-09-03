"""
NotificationService abstraction per module doc.
Isolates every actual gateway call (twilio, flask-mail) behind dispatch()
Nothing outside this file imports twilio & flask-mail directly
makes swapping providers later easy
"""

from flask import current_app
from flask_mail import Message as MailMessage
from twilio.rest import Client

from extensions import mail

class NotificationDispatchError(Exception):
    """
     Raised on any failure to actually send — missing config, provider
     error, etc. Callers decide how to record this (e.g. delivery_status="failed").
    """

def _get_twilio_client() -> Client:
    account_sid = current_app.config["TWILIO_ACCOUNT_SID"]
    auth_token = current_app.config["TWILIO_AUTH_TOKEN"]
    if not account_sid or not auth_token:
        raise NotificationDispatchError(
            "Twilio credentials not configured - set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN"
        )
    return Client(account_sid, auth_token)

def send_sms(
    to_phone_number: str,
    body: str
) -> str:
    "returns twilio message SID on success"
    client = _get_twilio_client()
    from_number = current_app.config("TWILIO_SMS_FROM_NUMBER")
    if not from_number:
        raise NotificationDispatchError(
           "TWILIO_SMS_FROM_NUMBER not configured." 
        )

    try:
        message = client.messages.create(
            to= to_phone_number,
            from_=from_number,
            body=body
        )
        return message.sid
    except Exception as exc:
        raise NotificationDispatchError(
            f"SMS dispatch failed:{exc}"
        ) from exc

def send_whatsapp(
    to_phone_number: str,
    body:str
) -> str:
    """
    sends a WhatsApp message using the Twilio API and returns the unique message identifier (the SID) if it succeeds
    """

    #set up twilio api connection
    client = _get_twilio_client()

    #looks up configured whatsapp number in app config
    from_number = current_app.config.get("TWILIO_WHATSAPP_FROM_NUMBER")

    if not from_number:
        raise NotificationDispatchError(
            "TWILIO_WHATSAPP_FROM_NUMBER not configured."
        )

    #sets up the "whatsapp" prefix if you forgot to add it
    to_whatsapp = to_phone_number if to_phone_number.startswith("whatsapp:") else f"whatsapp:{to_phone_number}"

    try:
        message = client.messages.create(
            to=to_whatsapp,
            from_=from_number,
            body=body
        )
        return message.sid

    except Exception as exc:
        raise NotificationDispatchError(
            f"WhatsApp dispatch failed: {exc}"
        ) from exc


def send_email(
    to_email: str,
    subject: str,
    body: str
) -> None:
    #send email to staff members
    msg= MailMessage(subject=subject, recipients=[to_email],body=body)
    try:
        mail.send(msg)
    except Exception as exc:
        raise NotificationDispatchError(
            f"Email dispatch failed: {exc}"
        ) from exc

def dispatch(
    channel: str,
    recipient_contact:str,
    body: str,
    subject: str = None
) -> str | None:
    """
    single entry point services.py should call- routes to the right gateway by channel
    returns a provider reference (twilio SID) for sms/whatsapp
    none for email
    """

    if channel == "sms":
       return send_sms(recipient_contact, body)
    elif channel == "whatsapp":
        return send_sms(recipient_contact, body)
    elif channel == "email":
        send_email(recipient_contact, subject or "SokoCredit Notification", body)
        return None
    else:
        raise ValueError(f"Unknown channel: {channel}")
    
        