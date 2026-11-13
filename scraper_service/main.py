import logging
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

if __package__:
    from .matching import classify_job, is_current, matches_entrepreneurship
    from .scrapers import (
        scrape_entrepreneurship_source,
        scrape_managed_site,
        scrape_vacancymail,
        scrape_vacancybox,
    )
else:
    from matching import classify_job, is_current, matches_entrepreneurship
    from scrapers import (
        scrape_entrepreneurship_source,
        scrape_managed_site,
        scrape_vacancymail,
        scrape_vacancybox,
    )
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("scraper_service")
API_URL = os.getenv(
    "SCRAPER_API_URL", "http://127.0.0.1:8000/api/internal/opportunities"
)
INTERNAL_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")
INTERVAL = max(900, int(os.getenv("SCRAPER_INTERVAL_SECONDS", "21600")))
ENTREPRENEURSHIP_SOURCES = [
    value.strip()
    for value in os.getenv("ENTREPRENEURSHIP_SOURCES", "").split(",")
    if value.strip()
]


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path not in {"/health", "/keepalive"}:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _submit(item: dict) -> None:
    response = requests.post(
        API_URL,
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        json=item,
        timeout=20,
    )
    response.raise_for_status()


def _managed_sites() -> list[dict]:
    response = requests.get(
        API_URL.rsplit("/", 1)[0] + "/sites",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("items", [])


def _mark_site_scanned(site_id: int) -> None:
    response = requests.post(
        API_URL.rsplit("/", 1)[0] + f"/sites/{site_id}/scanned",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        timeout=15,
    )
    response.raise_for_status()


def process_listing(item: dict) -> bool:
    if not is_current(item):
        return False
    if item.get("category") == "entrepreneurship":
        if not matches_entrepreneurship(item):
            return False
        item["summary"] = item.get("summary") or item["title"]
        _submit(item)
        return True
    if item.get("category") == "opportunity" and item.get("source", "").startswith("managed_site:"):
        _submit(item)
        return True
    recipient, reason = classify_job(item)
    if not recipient:
        return False
    item["matched_recipient"] = recipient
    item["match_reason"] = reason
    _submit(item)
    return True


def _run_source(name: str, scraper) -> int:
    try:
        items = scraper()
    except Exception:
        logger.exception("%s scrape failed; continuing with other sources", name)
        return 0
    sent = 0
    for item in items:
        try:
            sent += int(process_listing(item))
        except (requests.RequestException, ValueError, KeyError) as exc:
            logger.warning("Could not submit listing from %s: %s", name, exc)
    logger.info("%s: sent %d relevant listings", name, sent)
    return sent


def run_once() -> int:
    if not INTERNAL_TOKEN:
        raise RuntimeError("INTERNAL_API_TOKEN must be configured")
    total = _run_source("VacancyMail", scrape_vacancymail)
    total += _run_source("VacancyBox", scrape_vacancybox)
    for url in ENTREPRENEURSHIP_SOURCES:
        total += _run_source(
            f"Entrepreneurship source {url}",
            lambda source_url=url: scrape_entrepreneurship_source(source_url),
        )
    total += run_managed_sites()
    return total


def run_managed_sites() -> int:
    if not INTERNAL_TOKEN:
        raise RuntimeError("INTERNAL_API_TOKEN must be configured")
    total = 0
    try:
        sites = _managed_sites()
    except requests.RequestException:
        logger.exception("Could not load the website list; built-in scrapers will continue")
        return total
    for site in sites:
        try:
            listings = scrape_managed_site(site)
        except Exception:
            logger.exception("Managed website %s scan failed; it will be retried", site["name"])
            continue
        for item in listings:
            try:
                total += int(process_listing(item))
            except (requests.RequestException, ValueError, KeyError) as exc:
                logger.warning("Could not submit a listing from %s: %s", site["name"], exc)
        try:
            _mark_site_scanned(site["id"])
        except (requests.RequestException, KeyError) as exc:
            logger.warning("Could not update scan time for a configured website: %s", exc)
    return total


def main() -> None:
    port = int(os.getenv("PORT", "10000"))
    health_server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    Thread(target=health_server.serve_forever, daemon=True).start()
    logger.info("Independent scraper service started; interval=%s seconds", INTERVAL)
    next_built_in_scan = 0.0
    next_site_scan = 0.0
    while True:
        now = time.monotonic()
        if now >= next_built_in_scan:
            if not INTERNAL_TOKEN:
                logger.error("INTERNAL_API_TOKEN must be configured")
            else:
                next_built_in_scan = now + INTERVAL
                try:
                    _run_source("VacancyMail", scrape_vacancymail)
                    _run_source("VacancyBox", scrape_vacancybox)
                    for url in ENTREPRENEURSHIP_SOURCES:
                        _run_source(
                            f"Entrepreneurship source {url}",
                            lambda source_url=url: scrape_entrepreneurship_source(source_url),
                        )
                except Exception:
                    logger.exception("Built-in scraper cycle failed; the next cycle will retry")
        if now >= next_site_scan:
            next_site_scan = now + 60
            try:
                run_managed_sites()
            except Exception:
                logger.exception("Managed website scan failed; it will retry")
        time.sleep(10)


if __name__ == "__main__":
    main()
