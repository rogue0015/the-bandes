import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..config import settings
from ..database import connection
from ..schemas import ChangePasswordRequest, LoginRequest
from ..security import (
    COOKIE_NAME,
    SESSION_SECONDS,
    create_session_token,
    current_user,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["authentication"])


def provision_bootstrap_users() -> None:
    seeds = []
    for index in (1, 2):
        email = os.getenv(f"BOOTSTRAP_USER_{index}_EMAIL", "").strip()
        password = os.getenv(f"BOOTSTRAP_USER_{index}_PASSWORD", "")
        if email or password:
            if not email or len(password) < 12:
                raise RuntimeError(
                    f"Bootstrap user {index} needs an email and a password of at least 12 characters"
                )
            seeds.append((email, password))
    if not seeds:
        logger.warning("No bootstrap users configured; sign-in will remain unavailable")
        return
    with connection() as conn:
        for email, password in seeds:
            conn.execute(
                """INSERT OR IGNORE INTO users (email, password_hash, created_at)
                   VALUES (?, ?, ?)""",
                (email, hash_password(password), datetime.now(timezone.utc).isoformat()),
            )


@router.post("/login")
def login(body: LoginRequest, response: Response) -> dict[str, str]:
    with connection() as conn:
        user = conn.execute(
            "SELECT email, password_hash FROM users WHERE email = ? COLLATE NOCASE",
            (body.email,),
        ).fetchone()
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect",
        )
    response.set_cookie(
        COOKIE_NAME,
        create_session_token(user["email"]),
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return {"email": user["email"]}


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="strict")
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user)) -> dict[str, str | bool]:
    return {
        "email": user["email"],
        "can_manage_services": user["email"].lower() == settings.service_admin_email,
    }


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: dict = Depends(current_user),
) -> dict[str, bool]:
    with connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
        if row is None or not verify_password(body.current_password, row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(body.new_password), user["id"]),
        )
    return {"ok": True}
