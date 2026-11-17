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


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must not be empty")

    salt = secrets.token_bytes(16)
    password_hash = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
    )
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii")
    return f"scrypt$16384$8$1${encode(salt)}${encode(password_hash)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, n, r, p, encoded_salt, encoded_hash = stored_hash.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(encoded_salt)
        expected_hash = base64.urlsafe_b64decode(encoded_hash)
        actual_hash = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual_hash, expected_hash)
