"""
Database module for Alcalorpolitico scraper using asyncpg.
"""

import json
from datetime import date, datetime, timezone
from typing import List, Optional, Tuple
from dataclasses import dataclass

import asyncpg

from .config import Config
from .logger import logger


@dataclass
class InsertResult:
    """Result of a bulk insert operation."""
    total: int = 0
    inserted: int = 0
    updated: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


@dataclass
class ScrapeRunRecord:
    """Record for tracking scrape runs."""
    source: str
    run_type: str  # 'daily', 'backfill', 'manual'
    target_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    total_articles: int = 0
    successful_articles: int = 0
    failed_articles: int = 0
    new_articles: int = 0
    updated_articles: int = 0
    errors: Optional[dict] = None
    proxy_used: bool = False
    duration_seconds: Optional[float] = None


class DatabaseManager:
    """Manages PostgreSQL database connections and operations."""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._connected = False

    async def connect(self) -> None:
        """Create connection pool."""
        if self._connected:
            return

        try:
            self.pool = await asyncpg.create_pool(
                Config.DATABASE_URL,
                min_size=Config.DB_POOL_MIN,
                max_size=Config.DB_POOL_MAX,
                command_timeout=60,
                max_inactive_connection_lifetime=300.0,
            )
            self._connected = True
            logger.info(f"Database pool created (min={Config.DB_POOL_MIN}, max={Config.DB_POOL_MAX})")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def close(self) -> None:
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            self._connected = False
            logger.info("Database pool closed")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def article_exists(self, source: str, article_id: str) -> bool:
        """Check if article already exists."""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM articles WHERE source = $1 AND article_id = $2)",
                source, article_id
            )
            return result

    async def insert_article(self, article, source: str) -> Tuple[bool, bool]:
        """
        Insert or update a single article.

        Returns:
            Tuple of (success, was_new) - was_new is True if inserted, False if updated
        """
        async with self.pool.acquire() as conn:
            try:
                # Parse date
                pub_date = None
                if article.date:
                    try:
                        pub_date = datetime.strptime(article.date, '%Y-%m-%d').date()
                    except ValueError:
                        pass

                # Upsert article
                result = await conn.fetchrow("""
                    INSERT INTO articles (
                        source, article_id, url, title, subtitle, section,
                        author, location, publication_date, body, body_html,
                        keywords, scraped_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (source, article_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        subtitle = EXCLUDED.subtitle,
                        section = EXCLUDED.section,
                        author = EXCLUDED.author,
                        location = EXCLUDED.location,
                        publication_date = EXCLUDED.publication_date,
                        body = EXCLUDED.body,
                        body_html = EXCLUDED.body_html,
                        keywords = EXCLUDED.keywords,
                        updated_at = NOW()
                    RETURNING id, (xmax = 0) AS was_inserted
                """,
                    source,
                    article.article_id,
                    article.url,
                    article.title,
                    article.subtitle,
                    article.section,
                    article.source,  # This is the author/source field in the article
                    article.location,
                    pub_date,
                    article.body,
                    article.body_html,
                    article.keywords if article.keywords else [],
                    datetime.now(timezone.utc),
                )

                article_uuid = result['id']
                was_new = result['was_inserted']

                # Handle images
                if article.images:
                    # Delete existing images if updating
                    if not was_new:
                        await conn.execute(
                            "DELETE FROM article_images WHERE article_id = $1",
                            article_uuid
                        )

                    # Insert new images
                    for i, img in enumerate(article.images):
                        await conn.execute("""
                            INSERT INTO article_images (article_id, url, caption, position)
                            VALUES ($1, $2, $3, $4)
                        """, article_uuid, img.url, img.caption, i)

                return True, was_new

            except Exception as e:
                logger.error(f"Error inserting article {article.article_id}: {e}")
                return False, False

    async def bulk_insert_articles(self, articles: List, source: str) -> InsertResult:
        """
        Bulk insert articles with upsert logic.

        Args:
            articles: List of Article objects
            source: Source identifier (e.g., 'alcalorpolitico')

        Returns:
            InsertResult with counts and errors
        """
        result = InsertResult(total=len(articles))

        for article in articles:
            success, was_new = await self.insert_article(article, source)
            if success:
                if was_new:
                    result.inserted += 1
                else:
                    result.updated += 1
            else:
                result.errors.append(f"Failed to insert article {article.article_id}")

        logger.info(
            f"Bulk insert complete: {result.inserted} new, "
            f"{result.updated} updated, {len(result.errors)} errors"
        )
        return result

    async def log_scrape_run(self, run: ScrapeRunRecord) -> str:
        """Log a scraping run and return its ID."""
        async with self.pool.acquire() as conn:
            run_id = await conn.fetchval("""
                INSERT INTO scrape_runs (
                    source, run_type, target_date, start_date, end_date,
                    started_at, total_articles, successful_articles,
                    failed_articles, new_articles, updated_articles,
                    errors, status, proxy_used, duration_seconds
                ) VALUES ($1, $2, $3, $4, $5, NOW(), $6, $7, $8, $9, $10, $11, 'running', $12, $13)
                RETURNING id
            """,
                run.source,
                run.run_type,
                run.target_date,
                run.start_date,
                run.end_date,
                run.total_articles,
                run.successful_articles,
                run.failed_articles,
                run.new_articles,
                run.updated_articles,
                json.dumps(run.errors) if run.errors else None,
                run.proxy_used,
                run.duration_seconds,
            )
            return str(run_id)

    async def update_scrape_run(
        self,
        run_id: str,
        status: str,
        total_articles: int = 0,
        successful_articles: int = 0,
        failed_articles: int = 0,
        new_articles: int = 0,
        updated_articles: int = 0,
        errors: Optional[dict] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        """Update a scrape run record."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE scrape_runs SET
                    completed_at = NOW(),
                    status = $2,
                    total_articles = $3,
                    successful_articles = $4,
                    failed_articles = $5,
                    new_articles = $6,
                    updated_articles = $7,
                    errors = $8,
                    duration_seconds = $9
                WHERE id = $1
            """,
                run_id,
                status,
                total_articles,
                successful_articles,
                failed_articles,
                new_articles,
                updated_articles,
                json.dumps(errors) if errors else None,
                duration_seconds,
            )

    async def get_backfill_progress(self, source: str) -> Optional[date]:
        """Get the last completed date for backfill resume."""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT last_completed_date FROM backfill_progress
                WHERE source = $1 AND status = 'in_progress'
            """, source)
            return result

    async def update_backfill_progress(
        self,
        source: str,
        last_date: date,
        status: str = 'in_progress'
    ) -> None:
        """Update or create backfill progress record."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO backfill_progress (source, last_completed_date, status, started_at, updated_at)
                VALUES ($1, $2, $3, NOW(), NOW())
                ON CONFLICT (source) DO UPDATE SET
                    last_completed_date = EXCLUDED.last_completed_date,
                    status = EXCLUDED.status,
                    updated_at = NOW()
            """, source, last_date, status)

    async def get_article_count(self, source: Optional[str] = None) -> int:
        """Get total article count, optionally filtered by source."""
        async with self.pool.acquire() as conn:
            if source:
                return await conn.fetchval(
                    "SELECT COUNT(*) FROM articles WHERE source = $1",
                    source
                )
            return await conn.fetchval("SELECT COUNT(*) FROM articles")

    async def get_date_range(self, source: str) -> Tuple[Optional[date], Optional[date]]:
        """Get the min and max publication dates for a source."""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT MIN(publication_date), MAX(publication_date)
                FROM articles WHERE source = $1
            """, source)
            return result[0], result[1]
