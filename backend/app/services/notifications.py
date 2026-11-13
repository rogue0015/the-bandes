import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import requests

from ..database import connection
from .whatsapp import send_message

logger = logging.getLogger(__name__)


def _normalize_recipients(values: list[str]) -> list[str]:
    normalized = []
    for value in values:
        phone = "".join(character for character in str(value) if character.isdigit())
        if 7 <= len(phone) <= 15:
            normalized.append(phone)
    return normalized


def enqueue_notification(
    idempotency_key: str,
    message: str,
    recipients: list[str] | None = None,
    *,
    broadcast: bool = False,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    if broadcast and recipients:
        raise ValueError("A group broadcast cannot also specify recipients")
    normalized_recipients = _normalize_recipients(recipients or [])
    status = "pending" if normalized_recipients or broadcast else "skipped"
    last_error = (
        None
        if normalized_recipients or broadcast
        else "No valid WhatsApp recipient is configured"
    )
    if not normalized_recipients and not broadcast:
        logger.warning("Skipped an outbound notification without an explicit recipient")
    with connection() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO notification_outbox
               (idempotency_key, message, recipients_json, broadcast, status, scheduled_at,
                updated_at, last_error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                idempotency_key,
                message,
                json.dumps(normalized_recipients),
                int(broadcast),
                status,
                now,
                now,
                last_error,
            ),
        )


def _claim_pending() -> list[dict]:
    now = datetime.now(timezone.utc)
    stale_before = (now - timedelta(minutes=5)).isoformat()
    with connection() as conn:
        conn.execute(
            """UPDATE notification_outbox SET status = 'pending', updated_at = ?
               WHERE status = 'sending' AND updated_at < ?""",
            (now.isoformat(), stale_before),
        )
        rows = conn.execute(
            """SELECT id, message, recipients_json, broadcast FROM notification_outbox
               WHERE status = 'pending' AND scheduled_at <= ?
               ORDER BY scheduled_at LIMIT 25""",
            (now.isoformat(),),
        ).fetchall()
        claimed = []
        for row in rows:
            try:
                recipients = json.loads(row["recipients_json"])
            except (TypeError, json.JSONDecodeError):
                recipients = None
            recipients = (
                _normalize_recipients(recipients) if isinstance(recipients, list) else []
            )
            broadcast = bool(row["broadcast"])
            if not recipients and not broadcast:
                conn.execute(
                    """UPDATE notification_outbox SET status = 'skipped', updated_at = ?,
                       last_error = 'No valid WhatsApp recipient is configured'
                       WHERE id = ? AND status = 'pending'""",
                    (now.isoformat(), row["id"]),
                )
                logger.warning(
                    "Skipped pending notification %s without an explicit recipient",
                    row["id"],
                )
                continue
            result = conn.execute(
                """UPDATE notification_outbox SET status = 'sending', updated_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (now.isoformat(), row["id"]),
            )
            if result.rowcount:
                claimed.append(
                    {
                        "id": row["id"],
                        "message": row["message"],
                        "recipients": recipients,
                        "broadcast": broadcast,
                    }
                )
        return claimed


def _finish(notification_id: int, error: str | None) -> None:
    now = datetime.now(timezone.utc)
    with connection() as conn:
        if error is None:
            conn.execute(
                """UPDATE notification_outbox SET status = 'sent', attempts = attempts + 1,
                   updated_at = ?, last_error = NULL WHERE id = ?""",
                (now.isoformat(), notification_id),
            )
            return
        row = conn.execute(
            "SELECT attempts FROM notification_outbox WHERE id = ?", (notification_id,)
        ).fetchone()
        attempts = row["attempts"] if row else 0
        delay = min(5 * (2 ** min(attempts, 6)), 300)
        conn.execute(
            """UPDATE notification_outbox SET status = 'pending', attempts = attempts + 1,
               scheduled_at = ?, updated_at = ?, last_error = ? WHERE id = ?""",
            (
                (now + timedelta(seconds=delay)).isoformat(),
                now.isoformat(),
                error[:500],
                notification_id,
            ),
        )


def process_pending_notifications() -> None:
    for item in _claim_pending():
        try:
            send_message(
                item["message"], item["recipients"], broadcast=item["broadcast"]
            )
        except (requests.RequestException, RuntimeError, sqlite3.Error) as exc:
            logger.error("Notification %s delivery failed: %s", item["id"], exc)
            _finish(item["id"], str(exc))
        else:
            _finish(item["id"], None)
