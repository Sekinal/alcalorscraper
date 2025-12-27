"""
Historical backfill module for Alcalorpolitico scraper.
"""

import signal
import asyncio
from datetime import datetime, date, timedelta
from typing import Optional

from .config import Config
from .logger import logger
from .scraper import AlcalorPoliticoScraper
from .database import DatabaseManager


class BackfillManager:
    """Manages historical backfill operations with resume capability."""

    # Known earliest date for alcalorpolitico (can be discovered dynamically)
    DEFAULT_START_DATE = date(2003, 1, 1)

    def __init__(
        self,
        max_concurrent: int = 10,
        db_manager: Optional[DatabaseManager] = None,
        save_json: bool = True,
    ):
        self.max_concurrent = max_concurrent
        self.db = db_manager
        self.save_json = save_json
        self._shutdown_requested = False
        self._current_date: Optional[date] = None

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.warning(
            f"Shutdown signal received. Completing current date ({self._current_date})..."
        )
        self._shutdown_requested = True

    async def discover_earliest_date(self) -> date:
        """
        Discover the earliest date with articles using binary search.

        Returns:
            The earliest date with available articles
        """
        logger.info("Discovering earliest available date...")

        async with AlcalorPoliticoScraper(
            max_concurrent=1,
            db_manager=None,
            save_json=False,
        ) as scraper:
            # Binary search between DEFAULT_START_DATE and a known working date
            left = self.DEFAULT_START_DATE
            right = date.today() - timedelta(days=365)  # Start checking from a year ago
            earliest_found = right

            # First, verify the site has articles at all
            test_urls = await scraper.get_article_urls_by_date(right.strftime('%Y-%m-%d'))
            if not test_urls:
                logger.warning("Could not find articles on test date. Using default start.")
                return self.DEFAULT_START_DATE

            # Binary search for earliest date
            while left <= right:
                mid = left + (right - left) // 2
                mid_str = mid.strftime('%Y-%m-%d')

                urls = await scraper.get_article_urls_by_date(mid_str)

                if urls:
                    # Found articles, try going further back
                    earliest_found = mid
                    right = mid - timedelta(days=1)
                    logger.debug(f"Found {len(urls)} articles on {mid_str}, searching earlier")
                else:
                    # No articles, try more recent
                    left = mid + timedelta(days=1)
                    logger.debug(f"No articles on {mid_str}, searching later")

                # Small delay to be respectful
                await asyncio.sleep(0.5)

            logger.info(f"Earliest date with articles: {earliest_found}")
            return earliest_found

    async def get_resume_point(self) -> Optional[date]:
        """Get the last completed date from database for resume."""
        if not self.db:
            return None

        last_date = await self.db.get_backfill_progress(Config.SOURCE_NAME)
        if last_date:
            logger.info(f"Found resume point: {last_date}")
        return last_date

    async def run(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        resume: bool = False,
    ) -> None:
        """
        Run the backfill operation.

        Args:
            start_date: Optional start date (defaults to earliest available)
            end_date: Optional end date (defaults to yesterday)
            resume: Whether to resume from last checkpoint
        """
        # Determine end date (default: yesterday to avoid incomplete days)
        if end_date is None:
            end_date = date.today() - timedelta(days=1)

        # Determine start date
        if resume and self.db:
            resume_date = await self.get_resume_point()
            if resume_date:
                # Continue from the day after the last completed date
                start_date = resume_date - timedelta(days=1)
                logger.info(f"Resuming backfill from {start_date}")

        if start_date is None:
            if Config.BACKFILL_START_DATE:
                start_date = datetime.strptime(Config.BACKFILL_START_DATE, '%Y-%m-%d').date()
            else:
                start_date = await self.discover_earliest_date()

        # Calculate total days
        total_days = (end_date - start_date).days + 1
        logger.info(f"Backfill: {start_date} to {end_date} ({total_days} days)")

        # Track statistics
        stats = {
            'total_days': total_days,
            'completed_days': 0,
            'total_articles': 0,
            'new_articles': 0,
            'updated_articles': 0,
            'errors': 0,
            'start_time': datetime.now(),
        }

        # Process dates from most recent to oldest (working backwards)
        # This ensures we get the freshest content first
        current = end_date

        async with AlcalorPoliticoScraper(
            max_concurrent=self.max_concurrent,
            db_manager=self.db,
            save_json=self.save_json,
        ) as scraper:
            while current >= start_date and not self._shutdown_requested:
                self._current_date = current
                date_str = current.strftime('%Y-%m-%d')

                try:
                    daily_articles, db_result = await scraper.scrape_date(date_str)

                    stats['completed_days'] += 1
                    if daily_articles.metadata:
                        stats['total_articles'] += daily_articles.metadata.successful_articles
                        stats['errors'] += daily_articles.metadata.failed_articles

                    if db_result:
                        stats['new_articles'] += db_result.inserted
                        stats['updated_articles'] += db_result.updated

                    # Update backfill progress in database
                    if self.db:
                        await self.db.update_backfill_progress(
                            Config.SOURCE_NAME,
                            current,
                            'in_progress'
                        )

                    # Log progress periodically
                    if stats['completed_days'] % 10 == 0:
                        self._log_progress(stats, current, start_date)

                except Exception as e:
                    logger.error(f"Error processing {date_str}: {e}")
                    stats['errors'] += 1

                current -= timedelta(days=1)

        # Mark backfill as completed or paused
        if self.db:
            status = 'completed' if not self._shutdown_requested else 'paused'
            await self.db.update_backfill_progress(
                Config.SOURCE_NAME,
                self._current_date or start_date,
                status
            )

        # Final summary
        self._log_final_summary(stats)

    def _log_progress(self, stats: dict, current: date, start_date: date) -> None:
        """Log backfill progress."""
        elapsed = (datetime.now() - stats['start_time']).total_seconds()
        days_remaining = (current - start_date).days
        avg_time_per_day = elapsed / max(1, stats['completed_days'])
        eta_seconds = days_remaining * avg_time_per_day

        eta_str = str(timedelta(seconds=int(eta_seconds)))

        logger.info(
            f"Progress: {stats['completed_days']}/{stats['total_days']} days "
            f"({stats['total_articles']} articles, "
            f"{stats['new_articles']} new, {stats['updated_articles']} updated) "
            f"ETA: {eta_str}"
        )

    def _log_final_summary(self, stats: dict) -> None:
        """Log final backfill summary."""
        elapsed = datetime.now() - stats['start_time']

        logger.info("=" * 70)
        logger.info("Backfill Summary")
        logger.info("=" * 70)
        logger.info(f"Days processed: {stats['completed_days']}/{stats['total_days']}")
        logger.info(f"Total articles: {stats['total_articles']}")
        logger.info(f"New articles: {stats['new_articles']}")
        logger.info(f"Updated articles: {stats['updated_articles']}")
        logger.info(f"Errors: {stats['errors']}")
        logger.info(f"Duration: {elapsed}")

        if self._shutdown_requested:
            logger.info("Backfill paused - use --resume to continue")
        else:
            logger.info("Backfill completed successfully")
        logger.info("=" * 70)
