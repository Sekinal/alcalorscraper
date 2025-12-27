"""
Command-line interface for Alcalorpolitico scraper.
"""

import asyncio
import argparse
import sys
from datetime import datetime, timedelta

from .scraper import AlcalorPoliticoScraper
from .logger import logger
from .config import Config
from .database import DatabaseManager


async def run_health_check() -> bool:
    """Run health check on database connection."""
    logger.info("Running health check...")
    try:
        async with DatabaseManager() as db:
            if await db.health_check():
                count = await db.get_article_count(Config.SOURCE_NAME)
                logger.info(f"Database connection OK. Articles in DB: {count}")
                return True
            else:
                logger.error("Database health check failed")
                return False
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return False


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scrape articles from Alcalorpolitico.com"
    )
    parser.add_argument(
        '--date',
        type=str,
        help='Single date to scrape (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        help='Start date for range scraping (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        help='End date for range scraping (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--today',
        action='store_true',
        help='Scrape today\'s articles'
    )
    parser.add_argument(
        '--concurrent',
        type=int,
        default=10,
        help='Maximum concurrent requests (default: 10, max: 20)'
    )
    parser.add_argument(
        '--backfill',
        action='store_true',
        help='Run historical backfill from earliest available date'
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume interrupted backfill from last checkpoint'
    )
    parser.add_argument(
        '--db-only',
        action='store_true',
        help='Skip JSON file output, write only to database'
    )
    parser.add_argument(
        '--no-db',
        action='store_true',
        help='Skip database, write only JSON files'
    )
    parser.add_argument(
        '--health-check',
        action='store_true',
        help='Run health check and exit'
    )

    args = parser.parse_args()

    # Handle health check
    if args.health_check:
        success = await run_health_check()
        sys.exit(0 if success else 1)

    # Validate arguments
    has_scrape_args = any([
        args.date,
        args.today,
        (args.start_date and args.end_date),
        args.backfill
    ])
    if not has_scrape_args:
        parser.error(
            "Must specify --date, --today, --start-date/--end-date, or --backfill"
        )

    # Limit concurrency to reasonable values
    max_concurrent = min(max(1, args.concurrent), 20)

    # Determine storage options
    save_json = not args.db_only
    use_db = not args.no_db

    logger.info("=" * 70)
    logger.info("Alcalorpolitico Scraper Starting")
    logger.info(f"Output directory: {Config.OUTPUT_DIR}")
    logger.info(f"Max concurrent requests: {max_concurrent}")
    logger.info(f"Storage: JSON={save_json}, Database={use_db}")
    logger.info("=" * 70)

    # Initialize database if needed
    db_manager = None
    if use_db:
        try:
            db_manager = DatabaseManager()
            await db_manager.connect()
            logger.info("Database connected")
        except Exception as e:
            logger.warning(f"Database connection failed: {e}")
            logger.warning("Continuing with JSON-only mode")
            db_manager = None

    try:
        # Handle backfill mode
        if args.backfill:
            from .backfill import BackfillManager
            backfill = BackfillManager(
                max_concurrent=max_concurrent,
                db_manager=db_manager,
                save_json=save_json,
            )
            await backfill.run(resume=args.resume)
        else:
            # Regular scraping
            async with AlcalorPoliticoScraper(
                max_concurrent=max_concurrent,
                db_manager=db_manager,
                save_json=save_json,
            ) as scraper:
                if args.today:
                    # Scrape today plus the last N days to catch late-published articles
                    today = datetime.now()
                    rescrape_days = Config.RESCRAPE_DAYS

                    if rescrape_days > 0:
                        start_date = today - timedelta(days=rescrape_days)
                        logger.info(f"Scraping today + last {rescrape_days} days to catch late articles")
                        logger.info(f"Date range: {start_date.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')}")
                        await scraper.scrape_date_range(
                            start_date.strftime('%Y-%m-%d'),
                            today.strftime('%Y-%m-%d')
                        )
                    else:
                        date_str = today.strftime('%Y-%m-%d')
                        logger.info(f"Scraping today's date: {date_str}")
                        await scraper.scrape_date(date_str)

                elif args.date:
                    logger.info(f"Scraping single date: {args.date}")
                    await scraper.scrape_date(args.date)

                elif args.start_date and args.end_date:
                    logger.info(f"Scraping date range: {args.start_date} to {args.end_date}")
                    await scraper.scrape_date_range(args.start_date, args.end_date)

    finally:
        # Cleanup database connection
        if db_manager:
            await db_manager.close()

    logger.info("=" * 70)
    logger.info("Scraping completed successfully")
    logger.info("=" * 70)


def cli():
    """CLI entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
