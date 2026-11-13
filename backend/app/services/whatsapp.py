import logging

import requests

from ..config import settings

logger = logging.getLogger(__name__)


def send_message(
    text: str, recipients: list[str] | None = None, *, broadcast: bool = False
) -> None:
    if broadcast and recipients:
        raise ValueError("A WhatsApp group broadcast cannot also specify recipients")
    if not broadcast and not recipients:
        raise ValueError("At least one WhatsApp recipient is required")
    if not settings.internal_api_token:
        raise RuntimeError("WhatsApp service token is not configured")
    response = requests.post(
        f"{settings.whatsapp_service_url.rstrip('/')}/send",
        headers={"X-Internal-Token": settings.internal_api_token},
        json={"text": text, "recipients": recipients or [], "broadcast": broadcast},
        timeout=15,
    )
    response.raise_for_status()
