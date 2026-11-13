import logging
import ipaddress
import os
import re
import socket
import shutil
import time
from datetime import datetime, time as datetime_time
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

logger = logging.getLogger(__name__)
USER_AGENT = "BandesOpportunityCollector/1.0"
REQUEST_TIMEOUT = 15
MAX_PAGE_BYTES = 2_000_000
DATE_PATTERN = re.compile(
    r"\b(?:deadline|closing date|apply by|applications close|due date)"
    r"[^.\n]{0,80}?(\d{1,2}[/-]\d{1,2}[/-]20\d{2}|20\d{2}-\d{2}-\d{2})",
    re.IGNORECASE,
)


def _deadline(text: str) -> str | None:
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    value = match.group(1)
    try:
        date = (
            datetime.strptime(value, "%Y-%m-%d")
            if "-" in value and value[:4].isdigit()
            else datetime.strptime(value.replace("/", "-"), "%d-%m-%Y")
        )
        return datetime.combine(
            date.date(),
            datetime_time(23, 59),
            tzinfo=ZoneInfo(os.getenv("APP_TIMEZONE", "Africa/Harare")),
        ).isoformat()
    except ValueError:
        return None


def _parse_listing(html: str, base_url: str, source: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()
    for anchor in soup.select("a[href]"):
        title = anchor.get_text(" ", strip=True)
        href = urljoin(base_url, anchor.get("href", ""))
        parts = urlsplit(href)
        if (
            len(title) < 12
            or not parts.scheme.startswith("http")
            or parts.netloc == urlsplit(base_url).netloc and parts.path in {"/", "/jobs/"}
            or href in seen
        ):
            continue
        seen.add(href)
        card = anchor.find_parent(["article", "li", "div"]) or anchor.parent
        text = card.get_text(" ", strip=True)[:3000]
        results.append(
            {
                "url": href,
                "title": title[:300],
                "summary": text[:1500] or title,
                "category": "job",
                "source": source,
                "deadline": _deadline(text),
            }
        )
    return results


def scrape_vacancymail() -> list[dict]:
    url = "https://vacancymail.co.zw/jobs/"
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        stream=True,
    )
    response.raise_for_status()
    content = bytearray()
    for chunk in response.iter_content(chunk_size=8192):
        content.extend(chunk)
        if len(content) > MAX_PAGE_BYTES:
            raise ValueError("VacancyMail listing page exceeded the size limit")
    results = _parse_listing(
        content.decode(response.encoding or "utf-8", errors="replace"),
        response.url,
        "vacancymail.co.zw",
    )
    logger.info("VacancyMail: found %d candidate listings", len(results))
    return results


def scrape_vacancybox() -> list[dict]:
    url = "https://vacancybox.co.zw/"
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,1600")
    binary = os.getenv("CHROME_BIN")
    if binary:
        options.binary_location = binary
    driver_path = os.getenv("CHROMEDRIVER_PATH") or shutil.which("chromedriver")
    service = Service(executable_path=driver_path) if driver_path else Service()
    driver = webdriver.Chrome(options=options, service=service)
    try:
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(2)
        results = _parse_listing(driver.page_source, driver.current_url, "vacancybox.co.zw")
        logger.info("VacancyBox: found %d candidate listings", len(results))
        return results
    finally:
        driver.quit()


def scrape_entrepreneurship_source(url: str) -> list[dict]:
    response = requests.get(
        url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT, stream=True
    )
    response.raise_for_status()
    content = bytearray()
    for chunk in response.iter_content(chunk_size=8192):
        content.extend(chunk)
        if len(content) > MAX_PAGE_BYTES:
            raise ValueError("Entrepreneurship source exceeded the size limit")
    return [
        {**item, "category": "entrepreneurship", "source": urlsplit(url).netloc}
        for item in _parse_listing(
            content.decode(response.encoding or "utf-8", errors="replace"),
            response.url,
            "entrepreneurship",
        )
    ]


def scrape_managed_site(site: dict) -> list[dict]:
    final_url, html = _fetch_public_page(site["url"], site["name"])
    items = _parse_listing(
        html,
        final_url,
        f"managed_site:{site['id']}",
    )
    return [
        {
            **item,
            "category": "opportunity",
            "source": f"managed_site:{site['id']}",
        }
        for item in items
    ]


def _is_public_web_url(url: str) -> bool:
    parts = urlsplit(url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        return False
    try:
        addresses = socket.getaddrinfo(
            parts.hostname,
            parts.port or (443 if parts.scheme == "https" else 80),
        )
    except OSError:
        return False
    return bool(addresses) and all(
        ipaddress.ip_address(record[4][0]).is_global for record in addresses
    )


def _fetch_public_page(url: str, site_name: str) -> tuple[str, str]:
    current = url
    for _ in range(6):
        if not _is_public_web_url(current):
            raise ValueError(f"{site_name} redirected to a private or unsupported address")
        with requests.get(
            current,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            stream=True,
            allow_redirects=False,
        ) as response:
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                if not location:
                    raise ValueError(f"{site_name} returned an invalid redirect")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                content.extend(chunk)
                if len(content) > MAX_PAGE_BYTES:
                    raise ValueError(f"{site_name} page exceeded the size limit")
            return response.url, content.decode(response.encoding or "utf-8", errors="replace")
    raise ValueError(f"{site_name} redirected too many times")
