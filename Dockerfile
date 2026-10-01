FROM python:3.11-slim

# Runtime env
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# System deps for Chromium + Arabic fonts for the template
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        wget gnupg ca-certificates curl \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdbus-1-3 libdrm2 libxkbcommon0 \
        libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 \
        libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        fonts-noto-core fonts-noto-color-emoji fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# 1. Install Python dependencies (cached layer)
WORKDIR /srv
COPY requirements.txt /srv/requirements.txt
RUN pip install --upgrade pip && pip install -r /srv/requirements.txt

# 2. Install the Chromium binary Playwright drives
RUN playwright install chromium

# 3. Copy the source INTO /srv/app/ so it becomes the `app` package
COPY . /srv/app/

# 4. Persistent SQLite lives outside the source tree
RUN mkdir -p /data

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers 2 \
    --proxy-headers \
    --forwarded-allow-ips='*'"]