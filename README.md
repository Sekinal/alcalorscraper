# Alcalorpolitico Scraper

Production-grade news scraper for [Alcalorpolitico.com](https://www.alcalorpolitico.com), a Mexican political news site from Veracruz.

## Features

- **Async/Concurrent Scraping**: Uses `httpx` with semaphore-based concurrency control
- **Dual Storage**: PostgreSQL database + JSON files for traceability
- **Historical Backfill**: Scrape all articles from the site's beginning (2003+) with resume capability
- **Docker Ready**: Full containerization with automated daily cron via Ofelia scheduler
- **Multi-Scraper Architecture**: Database schema designed to support multiple news sources
- **Rate Limiting**: Configurable delays and retry logic with exponential backoff
- **Proxy Support**: Optional proxy configuration for distributed scraping

## Quick Start

### Prerequisites

- Python 3.12+
- [UV](https://github.com/astral-sh/uv) package manager
- Docker & Docker Compose (for containerized deployment)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd alcalorscraper

# Install dependencies
uv sync

# Run tests
uv run pytest tests/ -v
```

### Basic Usage

```bash
# Scrape today's articles (JSON only)
uv run python -m alcalorscraper.main --today --no-db

# Scrape a specific date
uv run python -m alcalorscraper.main --date 2024-12-25 --no-db

# Scrape a date range
uv run python -m alcalorscraper.main --start-date 2024-01-01 --end-date 2024-01-31 --no-db

# Adjust concurrency (default: 10, max: 20)
uv run python -m alcalorscraper.main --today --no-db --concurrent 5
```

## Docker Deployment

### Setup

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings
# Required: POSTGRES_PASSWORD
```

### Run with Docker Compose

```bash
# Start all services (PostgreSQL + scheduler)
docker compose up -d

# View logs
docker compose logs -f

# Manual scrape
docker compose run --rm scraper --today

# Historical backfill (all articles from 2003+)
docker compose run --rm scraper --backfill

# Resume interrupted backfill
docker compose run --rm scraper --backfill --resume

# Health check
docker compose run --rm scraper --health-check

# Stop services
docker compose down
```

### Automated Scheduling

The Ofelia scheduler runs daily scrapes automatically:
- **6:00 AM**: Scrape today's articles
- **8:00 AM**: Catch-up scrape for yesterday (if missed)
- **Sundays 12:00 PM**: Health check

## CLI Options

```
Usage: python -m alcalorscraper.main [OPTIONS]

Options:
  --date DATE           Single date to scrape (YYYY-MM-DD)
  --start-date DATE     Start date for range scraping
  --end-date DATE       End date for range scraping
  --today               Scrape today's articles
  --concurrent N        Max concurrent requests (default: 10, max: 20)
  --backfill            Run historical backfill from earliest date
  --resume              Resume interrupted backfill
  --db-only             Skip JSON files, write only to database
  --no-db               Skip database, write only JSON files
  --health-check        Run health check and exit
```

## Configuration

All settings can be configured via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://scraper:password@localhost:5432/news_scrapers` | PostgreSQL connection string |
| `DB_POOL_MIN` | `2` | Minimum database connections |
| `DB_POOL_MAX` | `10` | Maximum database connections |
| `PROXY_URL` | - | Optional proxy URL |
| `PROXY_USERNAME` | - | Proxy authentication username |
| `PROXY_PASSWORD` | - | Proxy authentication password |
| `REQUEST_DELAY` | `1.5` | Delay between requests (seconds) |
| `REQUEST_TIMEOUT` | `30` | Request timeout (seconds) |
| `MAX_RETRIES` | `3` | Max retry attempts per request |
| `LOG_LEVEL` | `INFO` | Logging level |
| `OUTPUT_DIR` | `data` | Output directory for JSON files |

## Project Structure

```
alcalorscraper/
├── src/alcalorscraper/
│   ├── __init__.py
│   ├── main.py          # CLI entry point
│   ├── scraper.py       # Core async scraper
│   ├── config.py        # Configuration management
│   ├── models.py        # Data models (Article, Image, etc.)
│   ├── logger.py        # Logging utilities
│   ├── database.py      # PostgreSQL layer (asyncpg)
│   └── backfill.py      # Historical backfill manager
├── tests/
│   ├── conftest.py      # Pytest fixtures
│   ├── test_scraper.py  # Scraper unit tests
│   └── test_database.py # Database tests
├── docker/
│   ├── init.sql         # Database schema
│   └── ofelia.ini       # Cron scheduler config
├── data/
│   ├── articles/        # JSON article files
│   ├── metadata/        # Scraping metadata
│   └── logs/            # Log files
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

## Database Schema

The database is designed for multi-scraper architecture:

```sql
-- Main articles table
CREATE TABLE articles (
    id UUID PRIMARY KEY,
    source VARCHAR(50) NOT NULL,      -- 'alcalorpolitico', 'other_source', etc.
    article_id VARCHAR(50) NOT NULL,  -- Original ID from source
    url TEXT NOT NULL,
    title TEXT,
    subtitle TEXT,
    section VARCHAR(100),
    author VARCHAR(255),
    location TEXT,
    publication_date DATE,
    body TEXT,
    body_html TEXT,
    keywords TEXT[],
    scraped_at TIMESTAMPTZ,
    UNIQUE (source, article_id)
);

-- Images table
CREATE TABLE article_images (
    id UUID PRIMARY KEY,
    article_id UUID REFERENCES articles(id),
    url TEXT NOT NULL,
    caption TEXT,
    position INT
);

-- Backfill progress (for resume capability)
CREATE TABLE backfill_progress (
    source VARCHAR(50) UNIQUE,
    last_completed_date DATE,
    status VARCHAR(20)
);
```

## Output Format

### JSON Files

Articles are saved to `data/articles/articles_YYYYMMDD.json`:

```json
{
  "date": "2024-12-25",
  "total_articles": 31,
  "articles": [
    {
      "article_id": "417654",
      "url": "https://www.alcalorpolitico.com/informacion/...",
      "title": "Article Title",
      "subtitle": "Article subtitle",
      "section": "Estado de Veracruz",
      "source": "Author Name",
      "location": "Xalapa, Ver. 25/12/2024",
      "date": "2024-12-25",
      "body": "Plain text article content...",
      "body_html": "<div>HTML content...</div>",
      "images": [
        {"url": "https://...", "caption": "Photo caption"}
      ],
      "keywords": ["keyword1", "keyword2"],
      "scraped_at": "2024-12-27T17:39:56+00:00"
    }
  ]
}
```

## Adding New Scrapers

The architecture supports multiple news sources. To add a new scraper:

1. Create a new package: `src/newsource/`
2. Implement the same interface as `AlcalorPoliticoScraper`
3. Use `SOURCE_NAME = "newsource"` in config
4. Articles will be stored in the same database with different `source` value

Query across all sources:
```sql
SELECT * FROM articles WHERE publication_date >= '2024-01-01';
SELECT * FROM articles WHERE source = 'alcalorpolitico';
```

## Development

```bash
# Install with dev dependencies
uv sync --all-extras

# Run tests
uv run pytest tests/ -v

# Run tests with coverage
uv run pytest tests/ --cov=src/alcalorscraper --cov-report=html

# Type checking (if using mypy)
uv run mypy src/
```

## Performance

Typical performance on a standard connection:
- **~15-20 articles/second** with 10 concurrent workers
- **~50-70 articles/day** on average for this news site
- **Full historical backfill**: ~8,000+ days of articles

## License

MIT License
