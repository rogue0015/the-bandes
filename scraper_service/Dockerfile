FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/scraper_service

COPY scraper_service/requirements.txt /app/scraper_service/requirements.txt
RUN pip install --no-cache-dir -r /app/scraper_service/requirements.txt

COPY scraper_service/main.py scraper_service/matching.py scraper_service/scrapers.py /app/scraper_service/

RUN useradd --create-home --uid 10002 scraper

ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver

USER scraper

CMD ["python", "main.py"]
