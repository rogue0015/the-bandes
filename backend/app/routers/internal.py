import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
import requests

from ..config import settings
from ..database import connection
from ..schemas import ScrapedOpportunity, WhatsAppChannelPost, WhatsAppInbound
from ..security import require_internal_token
from ..services.extractor import extract_channel_post, extract_opportunity
from ..services.notifications import enqueue_notification
from ..services.opportunities import (
    complete_opportunity_by_url,
    format_group_reply,
    format_summary,
    get_opportunity_by_source_ref,
    save_opportunity,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/internal", tags=["internal"])
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def _quoted_source_url(quoted_message: str | None) -> str | None:
    if not quoted_message:
        return None
    urls = {
        match.rstrip(".,;:!?)]}")
        for match in URL_PATTERN.findall(quoted_message)
    }
    return next(iter(urls)) if len(urls) == 1 else None


def _authorized(token: str | None) -> None:
    require_internal_token(token)


@router.post("/whatsapp/messages")
def receive_whatsapp_message(
    body: WhatsAppInbound,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> dict:
    _authorized(token)
    command = body.message.strip().rstrip(".!").casefold()
    if command in {"applied", "done"}:
        quoted_url = _quoted_source_url(body.quoted_message)
        if not quoted_url:
            return {
                "processed": 0,
                "completion": {
                    "updated": False,
                    "reply": "Reply to the bot's opportunity summary to mark it completed.",
                },
                "results": [],
            }
        try:
            record = complete_opportunity_by_url(quoted_url)
        except ValueError:
            record = None
        if not record:
            return {
                "processed": 0,
                "completion": {
                    "updated": False,
                    "reply": "I couldn't match that reply to a tracked opportunity.",
                },
                "results": [],
            }
        return {
            "processed": 1,
            "completion": {
                "updated": True,
                "reply": f"Marked as completed: {record['title']}. Pending reminders cleared.",
            },
            "results": [],
        }
    results = []
    for url in dict.fromkeys(str(item) for item in body.urls):
        try:
            extracted = extract_opportunity(url)
        except (requests.RequestException, ValueError, sqlite3.Error, RuntimeError) as exc:
            logger.warning("Could not extract details from a WhatsApp link: %s", exc)
            results.append(
                {
                    "url": url,
                    "created": False,
                    "reply": (
                        "I couldn't retrieve and classify that page, so I haven't "
                        "added it or scheduled a reminder. Please check the source link."
                    ),
                }
            )
            continue
        record, created = save_opportunity(extracted)
        results.append(
            {
                "url": url,
                "id": record["id"],
                "created": created,
                "reply": format_group_reply(record, created),
            }
        )
    return {"processed": len(results), "results": results}


@router.post("/whatsapp/channel-posts")
def receive_whatsapp_channel_post(
    body: WhatsAppChannelPost,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> dict:
    _authorized(token)
    if body.channel_name.strip().casefold() != settings.whatsapp_channel_name.casefold():
        raise HTTPException(status_code=403, detail="WhatsApp channel is not configured")
    source_ref = f"{body.channel_id}:{body.message_id}"
    existing = get_opportunity_by_source_ref(source_ref)
    if existing:
        return {
            "created": False,
            "duplicate": True,
            "title": existing["title"],
            "record_type": existing["record_type"],
            "summary": existing["summary"],
        }
    try:
        extracted = extract_channel_post(
            body.channel_name,
            str(body.post_url),
            body.message,
            [item.model_dump() for item in body.media],
            [str(url) for url in body.urls],
        )
        extracted["source_ref"] = source_ref
        record, created = save_opportunity(extracted)
    except (requests.RequestException, ValueError, sqlite3.Error, RuntimeError) as exc:
        logger.warning("Could not process a post from the configured WhatsApp channel: %s", exc)
        return {
            "created": False,
            "error": "The post could not be processed by Gemini",
        }
    if body.notify_group and record["record_type"] == "opportunity":
        enqueue_notification(
            f"opportunity-summary:{record['id']}",
            format_summary(record, prefix="IT Opportunities Zim"),
            broadcast=True,
        )
    return {
        "created": created,
        "duplicate": not created,
        "title": record["title"],
        "record_type": record["record_type"],
        "summary": record["summary"],
    }


@router.post("/opportunities")
def receive_scraped_opportunity(
    body: ScrapedOpportunity,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> dict:
    _authorized(token)
    is_entrepreneurship = body.category.lower() == "entrepreneurship"
    is_managed_site = body.source.startswith("managed_site:")
    if body.matched_recipient is None and not is_entrepreneurship and not is_managed_site:
        raise HTTPException(status_code=422, detail="A matching recipient is required")
    record, created = save_opportunity(body.model_dump(mode="python"))
    if created:
        recipient_phone = (
            settings.whatsapp_feli_phone
            if body.matched_recipient == "Feli"
            else settings.whatsapp_brandon_phone
            if body.matched_recipient == "Brandon"
            else ""
        )
        prefix = (
            "Entrepreneurship opportunity"
            if is_entrepreneurship
            else "Website opportunity"
            if is_managed_site and body.matched_recipient is None
            else f"Job match for {body.matched_recipient}"
        )
        if body.match_reason and not is_entrepreneurship:
            prefix += f" ({body.match_reason})"
        if recipient_phone:
            enqueue_notification(
                f"opportunity-summary:{record['id']}",
                format_summary(record, prefix=prefix),
                [recipient_phone],
            )
        elif is_entrepreneurship:
            enqueue_notification(
                f"opportunity-summary:{record['id']}",
                format_summary(record, prefix=prefix),
                broadcast=True,
            )
    return {"id": record["id"], "created": created}


@router.get("/sites")
def get_managed_sites(
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> dict:
    _authorized(token)
    with connection() as conn:
        rows = conn.execute(
            """SELECT id, name, url FROM managed_sites
               WHERE active = 1 AND (
                 scan_requested = 1 OR last_scanned_at IS NULL OR last_scanned_at <= ?
               ) ORDER BY id""",
            (
                (
                    datetime.now(timezone.utc)
                    - timedelta(seconds=settings.scraper_interval_seconds)
                ).isoformat(),
            ),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@router.post("/sites/{site_id}/scanned")
def mark_managed_site_scanned(
    site_id: int,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> dict[str, bool]:
    _authorized(token)
    with connection() as conn:
        conn.execute(
            "UPDATE managed_sites SET last_scanned_at = ?, scan_requested = 0 WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), site_id),
        )
    return {"ok": True}
