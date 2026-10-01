# Use an official Python slim image for a smaller final size
FROM python:3.11-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Install Chromium into a fixed shared path so it's found at runtime
# regardless of which user the container runs as.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install system dependencies:
# - wget, gnupg, ca-certificates: needed by Playwright's installer
# - The rest of the libraries below are Chromium's shared-library deps.
#   `playwright install --with-deps` would install them too, but doing it
#   here keeps the layer cache-friendly and the list explicit.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    curl \
    # Chromium runtime libraries
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    # Arabic fonts for the exam template (Amiri / Naskh fallbacks)
    fonts-noto-core \
    fonts-noto-color-emoji \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy and install Python dependencies first (for better Docker layer caching)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Install the Chromium binary used by Playwright for PDF rendering.
# --with-deps is omitted because we already installed the OS libraries above;
# this keeps the image reproducible and avoids apt calls at this stage.
RUN playwright install chromium

# Copy the entire project
COPY . .

# Ensure the SQLite directory exists. Dokploy will mount a named volume here,
# so the file survives redeploys.
RUN mkdir -p /app/data

# Expose the port your app runs on
EXPOSE 8000

# Final production command.
# --host 0.0.0.0: bind to all interfaces so Traefik/Dokploy can reach it
# --port ${PORT:-8000}: respect Dokploy's PORT env var, fall back to 8000
# --workers 2: FastAPI on a small VPS; bump if you have more vCPUs.
#   NOTE: each worker spawns its own Chromium for PDF rendering, so don't
#   over-provision. 2 workers is a good default for a 1–2 vCPU box.
# --proxy-headers: trust X-Forwarded-* from Traefik so request.client.host
#   in your rate limiter sees the real client IP, not the proxy.
CMD ["sh", "-c", "uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers 2 \
    --proxy-headers \
    --forwarded-allow-ips='*'"]