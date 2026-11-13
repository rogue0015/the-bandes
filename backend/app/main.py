import asyncio
import logging
import sqlite3
import time
from contextlib import asynccontextmanager
from threading import Lock

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import connection, initialize_database
from .routers import auth, internal, management, opportunities, reminders
from .routers.auth import provision_bootstrap_users
from .services.reminders import reminder_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
FRONTEND_DIR = settings.project_root / "frontend"
_keepalive_probe_lock = Lock()
_last_keepalive_probe = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    initialize_database()
    provision_bootstrap_users()
    stop_event = asyncio.Event()
    task = asyncio.create_task(reminder_loop(stop_event))
    app.state.reminder_stop = stop_event
    try:
        yield
    finally:
        stop_event.set()
        await task


app = FastAPI(title="Bandes Opportunities", version="1.0.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(opportunities.router)
app.include_router(reminders.router)
app.include_router(internal.router)
app.include_router(management.router)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    return {"status": "ok"}


@app.get("/keepalive", include_in_schema=False)
def keepalive() -> dict[str, str]:
    global _last_keepalive_probe
    with _keepalive_probe_lock:
        now = time.monotonic()
        should_probe = now - _last_keepalive_probe >= 60
        if should_probe:
            _last_keepalive_probe = now
    if not should_probe:
        return {"status": "ok"}

    services = (
        ("WhatsApp", settings.whatsapp_service_url),
        ("scraper", settings.scraper_service_url),
    )
    for service_name, service_url in services:
        if not service_url:
            continue
        try:
            response = requests.get(
                f"{service_url.rstrip('/')}/health",
                timeout=2,
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.warning("Keepalive could not reach the %s service", service_name)
    return {"status": "ok"}


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")
