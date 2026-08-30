import uuid
from typing import Optional
from supabase import create_client
from werkzeug.utils import secure_filename

#KYC document allowlist

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png"
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024 # 10MB in bytes

#raised for storage failiures
class StorageError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code
        self.message = message