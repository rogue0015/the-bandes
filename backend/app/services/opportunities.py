import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from ..config import settings
from ..database import connection

def _display_deadline(value: str | None) -> str:
    if not value:
        return "Not specified"
    deadline = datetime.fromisoformat(value)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=ZoneInfo(settings.timezone))
    return deadline.astimezone(ZoneInfo(settings.timezone)).strftime("%d %b %Y, %H:%M %Z")


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if (
        parts.scheme.lower() not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        raise ValueError("Only absolute HTTP(S) URLs can be saved")
    hostname = parts.hostname.encode("idna").decode("ascii").lower()
    netloc = hostname
    if parts.port and not (
        (parts.scheme.lower() == "http" and parts.port == 80)
        or (parts.scheme.lower() == "https" and parts.port == 443)
    ):
        netloc = f"{hostname}:{parts.port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(settings.timezone))
    return value.astimezone(timezone.utc).isoformat()


def _schedule_reminders(
    conn,
    opportunity_id: int,
    deadline: str | None,
    record_type: str = "opportunity",
) -> None:
    if not deadline or record_type == "article":
        return
    deadline_dt = datetime.fromisoformat(deadline)
    now = datetime.now(timezone.utc)
    for offset in (3, 1):
        scheduled = deadline_dt - timedelta(days=offset)
        if scheduled <= now:
            continue
        conn.execute(
            """INSERT OR IGNORE INTO reminders
               (opportunity_id, offset_days, scheduled_at, status, updated_at)
               VALUES (?, ?, ?, 'pending', ?)""",
            (opportunity_id, offset, scheduled.isoformat(), now.isoformat()),
        )


def save_opportunity(data: dict, summary_override: str | None = None) -> tuple[dict, bool]:
    url = canonicalize_url(str(data["url"]))
    source_ref = data.get("source_ref")
    now = datetime.now(timezone.utc).isoformat()
    deadline = _iso(data.get("deadline"))
    with connection() as conn:
        existing = conn.execute(
            """SELECT id FROM opportunities WHERE canonical_url = ?
               OR (? IS NOT NULL AND source_ref = ?)""",
            (url, source_ref, source_ref),
        ).fetchone()
        if existing:
            return get_opportunity(existing["id"], conn), False
        cursor = conn.execute(
            """INSERT INTO opportunities
               (canonical_url, source, title, organization, summary, record_type, category,
                source_ref,
                location, eligibility, deadline, matched_recipient, match_reason,
                status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
            (
                url,
                data.get("source", "group"),
                data["title"].strip(),
                data.get("organization"),
                (summary_override or data["summary"]).strip(),
                data.get("record_type", "opportunity"),
                data.get("category", "opportunity"),
                source_ref,
                data.get("location"),
                data.get("eligibility"),
                deadline,
                data.get("matched_recipient"),
                data.get("match_reason"),
                now,
                now,
            ),
        )
        opportunity_id = cursor.lastrowid
        _schedule_reminders(
            conn, opportunity_id, deadline, data.get("record_type", "opportunity")
        )
        return get_opportunity(opportunity_id, conn), True


def get_opportunity(opportunity_id: int, conn=None) -> dict | None:
    if conn is not None:
        row = conn.execute(
            "SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)
        ).fetchone()
        return dict(row) if row else None
    with connection() as db:
        row = db.execute(
            "SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)
        ).fetchone()
        return dict(row) if row else None


def get_opportunity_by_source_ref(source_ref: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM opportunities WHERE source_ref = ?", (source_ref,)
        ).fetchone()
        return dict(row) if row else None


def list_opportunities(status_filter: str | None = None) -> list[dict]:
    with connection() as conn:
        if status_filter:
            rows = conn.execute(
                """SELECT * FROM opportunities
                   WHERE status = ? AND record_type = 'opportunity' ORDER BY """
                "CASE WHEN deadline IS NULL THEN 1 ELSE 0 END, deadline, created_at DESC",
                (status_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM opportunities ORDER BY "
                "CASE WHEN deadline IS NULL THEN 1 ELSE 0 END, deadline, created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]


def update_status(opportunity_id: int, status: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT record_type FROM opportunities WHERE id = ?", (opportunity_id,)
        ).fetchone()
        if row is None or row["record_type"] != "opportunity":
            return None
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE opportunities SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, opportunity_id),
        )
        if status != "active":
            conn.execute(
                """UPDATE reminders SET status = 'skipped', updated_at = ?,
                   last_error = 'Opportunity is no longer active'
                   WHERE opportunity_id = ? AND status IN ('pending', 'sending')""",
                (now, opportunity_id),
            )
    return get_opportunity(opportunity_id)


def complete_opportunity_by_url(url: str) -> dict | None:
    canonical_url = canonicalize_url(url)
    now = datetime.now(timezone.utc).isoformat()
    with connection() as conn:
        row = conn.execute(
            """SELECT id FROM opportunities WHERE canonical_url = ?
               AND record_type = 'opportunity'""",
            (canonical_url,),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE opportunities SET status = 'completed', updated_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        conn.execute(
            """UPDATE reminders SET status = 'skipped', updated_at = ?,
               last_error = 'Opportunity marked completed from a WhatsApp reply'
               WHERE opportunity_id = ? AND status IN ('pending', 'sending')""",
            (now, row["id"]),
        )
        return get_opportunity(row["id"], conn)


def list_reminders() -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT r.id, r.offset_days, r.scheduled_at, r.status,
                      o.id AS opportunity_id, o.title, o.canonical_url, o.deadline,
                      o.status AS opportunity_status, o.record_type
               FROM reminders r JOIN opportunities o ON o.id = r.opportunity_id
               ORDER BY r.scheduled_at, o.title"""
        ).fetchall()
        return [dict(row) for row in rows]


def format_summary(opportunity: dict, prefix: str = "New opportunity") -> str:
    fields = [
        f"{prefix}: {opportunity['title']}",
        f"Organization: {opportunity.get('organization') or 'Not specified'}",
        f"Category: {opportunity.get('category') or 'Opportunity'}",
        f"Deadline: {_display_deadline(opportunity.get('deadline'))}",
        f"Details: {opportunity.get('summary') or 'See the source for details.'}",
    ]
    if opportunity.get("location"):
        fields.append(f"Location: {opportunity['location']}")
    if opportunity.get("eligibility"):
        fields.append(f"Eligibility: {opportunity['eligibility']}")
    fields.append(f"Source: {opportunity['canonical_url']}")
    return "\n".join(fields)


def format_group_reply(opportunity: dict, created: bool) -> str:
    summary = " ".join((opportunity.get("summary") or "").split())
    if len(summary) > 500:
        summary = f"{summary[:497].rstrip()}..."
    is_article = opportunity.get("record_type") == "article"
    prefix = "article summaries" if is_article else "opportunity registry"
    fields = [
        f"{'Added to' if created else 'Already in'} the {prefix}: {opportunity['title']}"
    ]
    if is_article:
        fields.append(f"Article summary: {summary or 'Open the source for details.'}")
    else:
        fields.extend(
            [
                f"Organization: {opportunity.get('organization') or 'Not specified'}",
                f"Deadline: {_display_deadline(opportunity.get('deadline'))}",
                f"Details: {summary or 'Open the source for details.'}",
            ]
        )
    fields.append(f"Source: {opportunity['canonical_url']}")
    return "\n".join(fields)


def counts() -> dict[str, int]:
    with connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
        active = conn.execute(
            """SELECT COUNT(*) FROM opportunities
               WHERE status = 'active' AND record_type = 'opportunity'"""
        ).fetchone()[0]
        upcoming = conn.execute(
            """SELECT COUNT(*) FROM opportunities WHERE status = 'active'
               AND record_type = 'opportunity' AND deadline >= ?""",
            (datetime.now(timezone.utc).isoformat(),),
        ).fetchone()[0]
    return {"total": total, "active": active, "upcoming": upcoming}
