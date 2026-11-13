FROM node:20-bookworm-slim

ENV PUPPETEER_SKIP_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    NODE_ENV=production

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/WhatsApp

COPY WhatsApp/package.json ./
RUN PUPPETEER_SKIP_DOWNLOAD=true npm install --omit=dev --no-audit --no-fund

COPY WhatsApp/index.js WhatsApp/profile-locks.js ./

RUN mkdir -p /app/WhatsApp/.wwebjs_auth /app/WhatsApp/.wwebjs_cache /data/whatsapp-queue \
    && chown -R node:node /app/WhatsApp /data/whatsapp-queue

ENV HOME=/home/node \
    WHATSAPP_HOST=0.0.0.0 \
    BACKEND_API_URL=http://backend:8000 \
    WHATSAPP_QUEUE_FILE=/data/whatsapp-queue/pending-messages.json

USER node

EXPOSE 3100

CMD ["node", "index.js"]
