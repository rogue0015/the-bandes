import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import Cookie, HTTPException, status

from .config import settings
from .database import connection

COOKIE_NAME = "bandes_session"
SESSION_SECONDS = 12 * 60 * 60
PASSWORD_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_session_token(email: str) -> str:
    payload = _encode(
        json.dumps(
            {"email": email, "expires": int(time.time()) + SESSION_SECONDS},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signature = hmac.new(
        settings.app_secret_key.encode("utf-8"), payload.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{payload}.{_encode(signature)}"


def _read_session(token: str) -> dict[str, Any]:
    try:
        payload, signature = token.split(".", 1)
        expected = hmac.new(
            settings.app_secret_key.encode("utf-8"),
            payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, _decode(signature)):
            raise ValueError("Invalid signature")
        data = json.loads(_decode(payload))
        if int(data["expires"]) <= int(time.time()):
            raise ValueError("Expired session")
        return data
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in"
        ) from None


def current_user(bandes_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    if not bandes_session or not settings.app_secret_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in"
        )
    data = _read_session(bandes_session)
    with connection() as conn:
        user = conn.execute(
            "SELECT id, email FROM users WHERE email = ? COLLATE NOCASE",
            (data["email"],),
        ).fetchone()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in"
        )
    return dict(user)


def require_internal_token(token: str | None) -> None:
    if not settings.internal_api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal service authentication is not configured",
        )
    if not token or not hmac.compare_digest(token, settings.internal_api_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
