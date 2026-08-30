import uuid

from typing import Optional
from supabase import create_client
from werkzeug.utils import secure_filename
from flask import current_app
#KYC document allowlist

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png"
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024 # 10MB in bytes

#raised for storage failures
class StorageError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code
        self.message = message

def _get_client():
    #lazily creates and caches one supabase client per app instance
    #this is useful for the different environments in app.config.py
    if "supabase" not in current_app.extensions:
        url = current_app.config["SUPABASE_URL"]
        key = current_app.config["SUPABASE_SERVICE_ROLE_KEY"]
        if not url or not key:
            raise StorageError(
                "Supabase storage is not configured (SUPABASE_URL / "
                "SUPABASE_SERVICE_ROLE_KEY missing).", 500
            )
        current_app.extensions["supabase"] = create_client(url, key)
    return current_app.extensions["supabase"]
    