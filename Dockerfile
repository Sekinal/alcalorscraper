# Multi-stage Dockerfile for Alcalorpolitico Scraper

FROM python:3.12-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv

# Copy all project files including README.md
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install --no-cache .

# Runtime stage
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN useradd --create-home --shell /bin/bash scraper

COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /app/data/articles /app/data/metadata /app/data/logs && \
    chown -R scraper:scraper /app

USER scraper

CMD ["python", "-m", "alcalorscraper", "--help"]
