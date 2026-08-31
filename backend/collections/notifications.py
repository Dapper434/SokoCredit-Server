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