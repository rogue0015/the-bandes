import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    project_root = PROJECT_ROOT
    database_path = Path(os.getenv("DATABASE_PATH", "backend/data/bandes.db"))
    app_secret_key = os.getenv("APP_SECRET_KEY", "")
    cookie_secure = _bool_env("APP_COOKIE_SECURE")
    timezone = os.getenv("APP_TIMEZONE", "Africa/Harare")
    internal_api_token = os.getenv("INTERNAL_API_TOKEN", "")
    whatsapp_service_url = os.getenv("WHATSAPP_SERVICE_URL", "http://127.0.0.1:3100")
    scraper_service_url = os.getenv("SCRAPER_SERVICE_URL", "").strip()
    whatsapp_group_name = os.getenv("WHATSAPP_GROUP_NAME", "Bandes")
    whatsapp_channel_name = os.getenv(
        "WHATSAPP_CHANNEL_NAME", "IT Opportunities Zim"
    ).strip()
    whatsapp_feli_phone = os.getenv("WHATSAPP_FELI_PHONE", "")
    whatsapp_brandon_phone = os.getenv("WHATSAPP_BRANDON_PHONE", "")
    service_admin_email = os.getenv(
        "SERVICE_ADMIN_EMAIL", os.getenv("BOOTSTRAP_USER_1_EMAIL", "brandonbande02@gmail.com")
    ).strip().lower()
    scraper_interval_seconds = max(900, int(os.getenv("SCRAPER_INTERVAL_SECONDS", "21600")))
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")

    @classmethod
    def database_file(cls) -> Path:
        path = cls.database_path
        if not path.is_absolute():
            path = cls.project_root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def validate(cls) -> None:
        if len(cls.app_secret_key) < 32 or "replace-with" in cls.app_secret_key:
            raise RuntimeError("Set APP_SECRET_KEY to a unique random value of at least 32 characters")
        if len(cls.internal_api_token) < 32 or "replace-with" in cls.internal_api_token:
            raise RuntimeError("Set INTERNAL_API_TOKEN to a unique random value of at least 32 characters")
        try:
            ZoneInfo(cls.timezone)
        except ZoneInfoNotFoundError as exc:
            raise RuntimeError(f"Unknown APP_TIMEZONE: {cls.timezone}") from exc


settings = Settings()
