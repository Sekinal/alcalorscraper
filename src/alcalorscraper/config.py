"""
Configuration module for Alcalorpolitico scraper.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Scraper configuration settings."""

    # Base URLs
    BASE_URL: str = "https://www.alcalorpolitico.com"
    ARCHIVE_URL: str = f"{BASE_URL}/informacion/notasarchivo.php"

    # HTTP Headers
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
    )

    # Proxy Configuration
    PROXY_URL: Optional[str] = os.getenv("PROXY_URL")
    PROXY_USERNAME: Optional[str] = os.getenv("PROXY_USERNAME")
    PROXY_PASSWORD: Optional[str] = os.getenv("PROXY_PASSWORD")

    # Rate Limiting
    REQUEST_DELAY: float = float(os.getenv("REQUEST_DELAY", "1.5"))
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))

    # Retry Configuration
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY: int = int(os.getenv("RETRY_DELAY", "2"))

    # Output Configuration
    OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", "data"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Database Configuration
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://scraper:password@localhost:5432/news_scrapers"
    )
    DB_POOL_MIN: int = int(os.getenv("DB_POOL_MIN", "2"))
    DB_POOL_MAX: int = int(os.getenv("DB_POOL_MAX", "10"))

    # Source identifier for multi-scraper support
    SOURCE_NAME: str = "alcalorpolitico"

    # Backfill Configuration
    BACKFILL_START_DATE: Optional[str] = os.getenv("BACKFILL_START_DATE")
    BACKFILL_BATCH_SIZE: int = int(os.getenv("BACKFILL_BATCH_SIZE", "7"))

    # Re-scrape recent days to catch late-published articles
    # When running --today, also re-scrape the last N days
    RESCRAPE_DAYS: int = int(os.getenv("RESCRAPE_DAYS", "3"))

    # Encoding
    SITE_ENCODING: str = "iso-8859-1"
    OUTPUT_ENCODING: str = "utf-8"

    @classmethod
    def get_proxy_url(cls) -> Optional[str]:
        """Build proxy URL for httpx."""
        if not cls.PROXY_URL:
            return None

        proxy_url = cls.PROXY_URL

        # Add credentials if provided
        if cls.PROXY_USERNAME and cls.PROXY_PASSWORD:
            # Parse and reconstruct URL with auth
            if "://" in proxy_url:
                scheme, rest = proxy_url.split("://", 1)
                proxy_url = f"{scheme}://{cls.PROXY_USERNAME}:{cls.PROXY_PASSWORD}@{rest}"

        return proxy_url

    @classmethod
    def setup_directories(cls) -> None:
        """Create necessary output directories."""
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (cls.OUTPUT_DIR / "articles").mkdir(exist_ok=True)
        (cls.OUTPUT_DIR / "metadata").mkdir(exist_ok=True)
        (cls.OUTPUT_DIR / "logs").mkdir(exist_ok=True)


# Initialize directories on import
Config.setup_directories()
