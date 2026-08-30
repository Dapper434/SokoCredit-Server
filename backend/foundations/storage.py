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


def build_object_path(
    module_prefix:str,
    owner_id: int,
    original_filename: str
) -> str:
    #builds the objects path within th shared bucket
    
    #generate a unique filename for security
    safe_name = secure_filename(original_filename) or "file"
    #add a random prefix to ensure uniqueness
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"

    return f"{module_prefix}/{owner_id}/{unique_name}"


def validate_upload(
    content_type: str,
    size_bytes:int
) -> None:
    #called before upload_file() to validate file upload
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise StorageError("Unsupported file type.", 400)

    if size_bytes > MAX_FILE_SIZE_BYTES:
        raise StorageError("File too large.", 413)


def upload_file(
    path: str,
    file_bytes: bytes,
    content_type: str
) -> str:
    """
    uploads to the shared bucket and returns the ob path
    path then gets saved to the document row's storage_path column
    """
    client = _get_client()
    bucket = current_app.config["SUPABASE_STORAGE_BUCKET"]

    try:
        client.storage.from_(bucket).upload(
            path,file_bytes,{"content-type": content_type}
        )
    except Exception as exc:
        raise StorageError(f"Upload failed:{exc}", 502)
    return path

def generate_signed_url(
    path: str,
    expires_in: Optional[int] = None
) -> str:
    """
    called by download routes to generate a signed_url
    this grants access to fetch the file directly from Supabase for the next 'expires_in' seconds
    routes perform rbac checks to confirm who can download the file
    """

    client = _get_client()
    bucket = current_app.config["SUPABASE_STORAGE_BUCKET"]
    expires_in = expires_in or current_app.config["SIGNED_URL_EXPIRES_IN_SECONDS"]

    try:
        response = client.storage.from_(bucket).create_signed_url(
            path, expires_in
        )
    except Exception as exc:
        raise StorageError(f"Could not generate signed URL: {exc}", 502)

    return response["signedURL"]