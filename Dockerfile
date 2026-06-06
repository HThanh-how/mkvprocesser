FROM python:3.12-slim

# ffmpeg/ffprobe from the distro (cross-platform: no bundled Windows binaries).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Build deps first for layer caching. docs/mkvtools.md is referenced by
# pyproject's `readme`, so it must be present at build time.
COPY pyproject.toml ./
COPY docs/mkvtools.md ./docs/mkvtools.md
COPY config.example.yaml ./
COPY src/mkvtools ./src/mkvtools

# Headless image needs upload + web GUI integrations (not the PySide6 desktop extra).
RUN pip install --no-cache-dir ".[all]"

# Runtime dirs (also bind-mounted by docker-compose).
RUN mkdir -p inbox work done secrets

CMD ["mkvtools", "watch"]
