import os
import base64
import hashlib
import hmac
import secrets
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()


def get_fernet(key: str | None = None) -> Fernet:
    encryption_key = key or os.getenv("SUPABASE_ENCRYPTION_KEY")
    if not encryption_key:
        raise RuntimeError(
            "SUPABASE_ENCRYPTION_KEY must be configured to handle "
            "encrypted user credentials"
        )
    return Fernet(encryption_key.encode("ascii"))


def encrypt(value: str | None, key: str | None = None) -> str | None:
    if value is None:
        return None
    return get_fernet(key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value: str | None, key: str | None = None) -> str | None:
    if value is None:
        return None
    return get_fernet(key).decrypt(value.encode("ascii")).decode("utf-8")
