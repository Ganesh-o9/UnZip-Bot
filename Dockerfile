# NovaUnzip High-Performance Telegram Extraction Engine
FROM python:3.11-slim-bookworm

# Set environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WORKDIR=/app/downloads

# Install core extraction utilities & ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    p7zip-full \
    p7zip-rar \
    unrar \
    tar \
    xz-utils \
    bzip2 \
    zstd \
    ffmpeg \
    curl \
    gcc \
    libffi-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency definition
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create downloads volume mount point
RUN mkdir -p /app/downloads && chmod 777 /app/downloads

VOLUME ["/app/downloads"]

CMD ["python3", "ultra_unzip_bot.py"]
