import ipaddress
import logging
import sqlite3
import socket
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests
from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..config import settings
from ..database import connection
from ..schemas import ManagedSiteCreate
from ..security import current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["management"])


def _service_admin(user: dict = Depends(current_user)) -> dict:
    if user["email"].lower() != settings.service_admin_email:
        raise HTTPException(status_code=403, detail="Only the service administrator can manage this")
    return user


def _require_public_url(url: str) -> None:
    parts = urlsplit(url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        raise HTTPException(status_code=422, detail="Enter a public HTTP or HTTPS website URL")
    try:
        addresses = socket.getaddrinfo(
            parts.hostname,
            parts.port or (443 if parts.scheme == "https" else 80),
        )
    except OSError:
        raise HTTPException(status_code=422, detail="The website hostname could not be resolved") from None
    if not addresses or any(
        not ipaddress.ip_address(record[4][0]).is_global for record in addresses
    ):
        raise HTTPException(status_code=422, detail="Private and local network addresses are not allowed")


def _whatsapp_request(method: str, path: str):
    if not settings.internal_api_token:
        raise HTTPException(status_code=503, detail="WhatsApp service authentication is not configured")
    try:
        response = requests.request(
            method,
            f"{settings.whatsapp_service_url.rstrip('/')}{path}",
            headers={"X-Internal-Token": settings.internal_api_token},
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.warning("WhatsApp service is unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="WhatsApp service is not reachable") from exc
    if response.status_code == 404 and path == "/qr":
        return {"qr": None}
    if response.status_code >= 400:
        raise HTTPException(
            status_code=503,
            detail="WhatsApp service is not ready",
        )
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="WhatsApp service returned an invalid response") from exc


@router.get("/api/whatsapp/status")
def whatsapp_status(
    response: Response,
    user: dict = Depends(_service_admin),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    state = _whatsapp_request("GET", "/status")
    if state.get("state") == "qr":
        qr = _whatsapp_request("GET", "/qr")
        state["qr"] = qr.get("qr")
    else:
        state["qr"] = None
    return state


@router.post("/api/whatsapp/start")
def whatsapp_start(user: dict = Depends(_service_admin)) -> dict:
    return _whatsapp_request("POST", "/start")


@router.post("/api/whatsapp/channel/test-last-10")
def test_whatsapp_channel(user: dict = Depends(_service_admin)) -> dict:
    return _whatsapp_request("POST", "/channels/test-last-10")


@router.get("/api/sites")
def list_sites(user: dict = Depends(_service_admin)) -> dict:
    with connection() as conn:
        rows = conn.execute(
            """SELECT id, name, url, active, created_at, last_scanned_at, scan_requested
               FROM managed_sites ORDER BY created_at DESC"""
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@router.post("/api/sites", status_code=status.HTTP_201_CREATED)
def add_site(
    body: ManagedSiteCreate,
    user: dict = Depends(_service_admin),
) -> dict:
    url = str(body.url).rstrip("/")
    _require_public_url(url)
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with connection() as conn:
            cursor = conn.execute(
                """INSERT INTO managed_sites (name, url, active, created_at)
                   VALUES (?, ?, 1, ?)""",
                (body.name.strip(), url, created_at),
            )
            site_id = cursor.lastrowid
            row = conn.execute(
                """SELECT id, name, url, active, created_at, last_scanned_at, scan_requested
                   FROM managed_sites WHERE id = ?""",
                (site_id,),
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="This website is already on your list") from exc
        raise
    return dict(row)


@router.delete("/api/sites/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_site(site_id: int, user: dict = Depends(_service_admin)) -> None:
    with connection() as conn:
        result = conn.execute("DELETE FROM managed_sites WHERE id = ?", (site_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Website not found")


@router.post("/api/sites/{site_id}/scan")
def request_site_scan(site_id: int, user: dict = Depends(_service_admin)) -> dict[str, bool]:
    with connection() as conn:
        result = conn.execute(
            "UPDATE managed_sites SET scan_requested = 1 WHERE id = ?",
            (site_id,),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Website not found")
    return {"queued": True}
