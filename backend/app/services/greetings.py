from datetime import datetime, time
from zoneinfo import ZoneInfo

from ..config import settings
from .notifications import enqueue_notification

DAILY_GREETINGS = (
    ("morning", time(7, 0), "Good morning my Queen Feli"),
    ("afternoon", time(13, 0), "Good afternoon my Queen Feli"),
    ("night", time(21, 0), "Good night my Queen Feli"),
)


def _feli_phone() -> str:
    phone = "".join(
        character for character in settings.whatsapp_feli_phone if character.isdigit()
    )
    return phone if 7 <= len(phone) <= 15 else ""


def schedule_daily_greetings() -> None:
    phone = _feli_phone()
    if not phone:
        return
    zone = ZoneInfo(settings.timezone)
    now = datetime.now(zone)
    for label, at, text in DAILY_GREETINGS:
        scheduled = datetime.combine(now.date(), at, tzinfo=zone)
        if scheduled <= now:
            continue
        enqueue_notification(
            f"greeting:{label}:{now.date().isoformat()}",
            text,
            [phone],
            scheduled_at=scheduled,
        )
