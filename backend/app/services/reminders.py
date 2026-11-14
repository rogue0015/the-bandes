import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import requests

from ..config import settings
from ..database import connection
from .greetings import schedule_daily_greetings
from .notifications import process_pending_notifications
from .opportunities import get_opportunity, format_summary
from .whatsapp import send_message

logger = logging.getLogger(__name__)


def _claim_due() -> list[tuple[int, int, dict]]:
    now = datetime.now(timezone.utc)
    stale = (now - timedelta(minutes=5)).isoformat()
    with connection() as conn:
        conn.execute(
            """UPDATE reminders SET status = 'pending', updated_at = ?
               WHERE status = 'sending' AND updated_at < ?""",
            (now.isoformat(), stale),
        )
        conn.execute(
            """UPDATE reminders SET status = 'skipped', updated_at = ?,
               last_error = 'Deadline passed before reminder delivery'
               WHERE status = 'pending' AND scheduled_at <= ?
                 AND opportunity_id IN (
                   SELECT id FROM opportunities
                   WHERE deadline IS NOT NULL AND deadline <= ?
                 )""",
            (now.isoformat(), now.isoformat(), now.isoformat()),
        )
        rows = conn.execute(
            """SELECT r.id, r.offset_days, o.id AS opportunity_id
               FROM reminders r JOIN opportunities o ON o.id = r.opportunity_id
               WHERE r.status = 'pending' AND r.scheduled_at <= ?
                 AND o.status = 'active'
               ORDER BY r.scheduled_at LIMIT 25""",
            (now.isoformat(),),
        ).fetchall()
        claimed = []
        for row in rows:
            result = conn.execute(
                """UPDATE reminders SET status = 'sending', updated_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (now.isoformat(), row["id"]),
            )
            if result.rowcount:
                claimed.append((row["id"], row["offset_days"], get_opportunity(row["opportunity_id"], conn)))
        return claimed


def _finish(reminder_id: int, error: str | None) -> None:
    now = datetime.now(timezone.utc)
    with connection() as conn:
        if error is None:
            conn.execute(
                """UPDATE reminders SET status = 'sent', attempts = attempts + 1,
                   updated_at = ?, last_error = NULL WHERE id = ?""",
                (now.isoformat(), reminder_id),
            )
        else:
            retry_at = (now + timedelta(minutes=5)).isoformat()
            conn.execute(
                """UPDATE reminders SET status = 'pending', attempts = attempts + 1,
                   scheduled_at = ?, updated_at = ?, last_error = ? WHERE id = ?""",
                (retry_at, now.isoformat(), error[:500], reminder_id),
            )


def _skip(reminder_id: int, reason: str) -> None:
    with connection() as conn:
        conn.execute(
            """UPDATE reminders SET status = 'skipped', updated_at = ?, last_error = ?
               WHERE id = ?""",
            (datetime.now(timezone.utc).isoformat(), reason[:500], reminder_id),
        )


def _notification_target(opportunity: dict) -> dict | None:
    recipient = opportunity.get("matched_recipient")
    if recipient in {"Feli", "Brandon"}:
        configured_phone = (
            settings.whatsapp_feli_phone
            if recipient == "Feli"
            else settings.whatsapp_brandon_phone
        )
        phone = "".join(character for character in configured_phone if character.isdigit())
        if 7 <= len(phone) <= 15:
            return {"recipients": [phone], "broadcast": False}
        return None
    if (
        opportunity.get("source") == "group"
        or str(opportunity.get("category", "")).lower() == "entrepreneurship"
        or str(opportunity.get("source", "")).startswith("whatsapp_channel:")
    ):
        return {"recipients": [], "broadcast": True}
    return None


def process_due_reminders() -> None:
    for reminder_id, offset_days, opportunity in _claim_due():
        if not opportunity:
            _finish(reminder_id, "Opportunity no longer exists")
            continue
        deadline = datetime.fromisoformat(opportunity["deadline"])
        if deadline <= datetime.now(timezone.utc):
            with connection() as conn:
                conn.execute(
                    """UPDATE reminders SET status = 'skipped', updated_at = ?,
                       last_error = 'Deadline passed before reminder delivery'
                       WHERE id = ?""",
                    (datetime.now(timezone.utc).isoformat(), reminder_id),
                )
            continue
        target = _notification_target(opportunity)
        if target is None:
            _skip(reminder_id, "No explicit WhatsApp recipient is configured")
            continue
        try:
            send_message(
                format_summary(
                    opportunity, prefix=f"Reminder: deadline in {offset_days} day(s)"
                ),
                **target,
            )
        except (requests.RequestException, RuntimeError, sqlite3.Error) as exc:
            logger.error("Reminder delivery failed for record %s: %s", opportunity["id"], exc)
            _finish(reminder_id, str(exc))
        else:
            _finish(reminder_id, None)


async def reminder_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(schedule_daily_greetings)
            await asyncio.to_thread(process_pending_notifications)
            await asyncio.to_thread(process_due_reminders)
        except Exception:
            logger.exception("Notification cycle failed; the next cycle will retry")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=5)
        except asyncio.TimeoutError:
            pass
