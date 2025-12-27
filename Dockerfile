# Multi-stage Dockerfile for Alcalorpolitico Scraper

# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

# Install UV for fast package management
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/

# Create virtual environment and install dependencies
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install --no-cache .

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash scraper

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ ./src/

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

# Create data directory
RUN mkdir -p /app/data/articles /app/data/metadata /app/data/logs && \
    chown -R scraper:scraper /app

# Switch to non-root user
USER scraper

# Health check
HEALTHCHECK --interval=60s --timeout=30s --start-period=10s --retries=3 \
    CMD python -c "from alcalorscraper.database import DatabaseManager; import asyncio; asyncio.run(DatabaseManager().connect())" || exit 1

# Default command
ENTRYPOINT ["python", "-m", "alcalorscraper.main"]
CMD ["--help"]
