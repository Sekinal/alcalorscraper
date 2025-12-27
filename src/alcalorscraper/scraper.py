"""
Main scraper module for Alcalorpolitico - OPTIMIZED VERSION.
"""

import asyncio
import re
import html
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import Config
from .logger import logger
from .models import Article, Image, ScrapingMetadata, DailyArticles
from .database import DatabaseManager, InsertResult

# Type hint for optional import
try:
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from .database import DatabaseManager
except ImportError:
    pass


class AlcalorPoliticoScraper:
    """Scraper for Alcalorpolitico news site."""

    def __init__(
        self,
        max_concurrent: int = 10,
        db_manager: Optional[DatabaseManager] = None,
        save_json: bool = True,
    ):
        """
        Initialize scraper.

        Args:
            max_concurrent: Maximum number of concurrent requests (default: 10)
            db_manager: Optional database manager for PostgreSQL storage
            save_json: Whether to save JSON files (default: True)
        """
        self.config = Config
        self.client: Optional[httpx.AsyncClient] = None
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_concurrent = max_concurrent
        self.db = db_manager
        self.save_json = save_json

    async def __aenter__(self):
        """Async context manager entry."""
        await self._setup_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._close_client()

    async def _setup_client(self) -> None:
        """Setup HTTP client with optional proxy."""
        proxy_url = self.config.get_proxy_url()

        # httpx uses 'proxy' parameter (singular) or 'mounts' for different protocols
        client_kwargs = {
            "headers": {"User-Agent": self.config.USER_AGENT},
            "timeout": self.config.REQUEST_TIMEOUT,
            "follow_redirects": True,
            "limits": httpx.Limits(max_keepalive_connections=20, max_connections=50)
        }

        if proxy_url:
            client_kwargs["proxy"] = proxy_url
            logger.info(f"Using proxy: {proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url}")

        self.client = httpx.AsyncClient(**client_kwargs)
        logger.info(f"Max concurrent requests: {self.max_concurrent}")

    async def _close_client(self) -> None:
        """Close HTTP client."""
        if self.client:
            await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException))
    )
    async def _fetch_url(self, url: str) -> str:
        """Fetch URL with retry logic."""
        logger.debug(f"Fetching: {url}")
        response = await self.client.get(url)
        response.raise_for_status()
        response.encoding = self.config.SITE_ENCODING
        return response.text

    async def get_article_urls_by_date(self, date_str: str) -> List[str]:
        """Get all article URLs for a specific date."""
        url = f"{self.config.ARCHIVE_URL}?fn={date_str}"

        try:
            html_content = await self._fetch_url(url)
            soup = BeautifulSoup(html_content, 'lxml')

            article_urls = []
            contenido_div = soup.find('div', class_='contenido')

            if not contenido_div:
                logger.warning(f"No content div found for {date_str}")
                return article_urls

            for link in contenido_div.find_all('a', href=True):
                href = link['href']

                if href.startswith('/informacion/') and href.endswith('.html'):
                    full_url = self.config.BASE_URL + href
                    article_urls.append(full_url)

            logger.info(f"Found {len(article_urls)} articles for {date_str}")
            return article_urls

        except Exception as e:
            logger.error(f"Error getting URLs for {date_str}: {e}", exc_info=True)
            return []

    def _extract_images_from_gallery(self, soup: BeautifulSoup) -> List[Image]:
        """Extract images from iLightBox gallery JavaScript."""
        images = []
        scripts = soup.find_all('script')

        for script in scripts:
            if script.string and '$.iLightBox' in script.string:
                match = re.search(r'\$.iLightBox\(\s*\[([^\]]+)\]', script.string, re.DOTALL)
                if match:
                    array_content = match.group(1)

                    image_matches = re.finditer(
                        r'\{\s*URL:\s*"([^"]+)"\s*,\s*caption:\s*"([^"]+)"\s*\}',
                        array_content
                    )

                    for img_match in image_matches:
                        images.append(Image(
                            url=self.config.BASE_URL + img_match.group(1),
                            caption=html.unescape(img_match.group(2))
                        ))

        return images

    async def extract_article_content(self, article_url: str, index: int = 0, total: int = 0) -> Optional[Article]:
        """Extract full content from an article page with semaphore control."""
        async with self.semaphore:
            try:
                if total > 0:
                    logger.info(f"[{index}/{total}] Scraping: {article_url}")

                html_content = await self._fetch_url(article_url)
                soup = BeautifulSoup(html_content, 'lxml')

                article = Article(
                    article_id=None,
                    url=article_url,
                    title=None,
                    subtitle=None,
                    section=None,
                    source=None,
                    location=None,
                    date=None,
                    body=None,
                    body_html=None
                )

                # Extract article ID from URL
                id_match = re.search(r'-(\d+)\.html$', article_url)
                if id_match:
                    article.article_id = id_match.group(1)

                # Extract metadata from header
                header = soup.find('div', id='areasuperiorColumna')
                if header:
                    seccion = header.find('p', id='seccion')
                    if seccion:
                        article.section = seccion.get_text(strip=True).replace('Sección:', '').strip()

                    h1 = header.find('h1')
                    if h1:
                        article.title = html.unescape(h1.get_text(strip=True))

                    h2 = header.find('h2')
                    if h2:
                        article.subtitle = html.unescape(h2.get_text(strip=True))

                    h3 = header.find('h3')
                    if h3:
                        lugar_span = h3.find('span', id='lugar')
                        if lugar_span:
                            lugar_text = lugar_span.get_text(strip=True)
                            article.location = lugar_text

                            date_match = re.search(r'(\d{2})/(\d{2})/(\d{4})', lugar_text)
                            if date_match:
                                article.date = f"{date_match.group(3)}-{date_match.group(2)}-{date_match.group(1)}"

                            source_text = h3.get_text().replace(lugar_text, '').strip()
                            article.source = source_text

                # Extract body content
                body_div = soup.find('div', class_='cuerponota')
                if body_div:
                    for ad in body_div.find_all(['ins', 'script']):
                        ad.decompose()

                    article.body_html = str(body_div)

                    body_text = body_div.get_text(separator='\n', strip=True)
                    body_text = re.sub(r'\n\s*\n+', '\n\n', body_text)
                    article.body = html.unescape(body_text)

                # Extract images
                article.images = self._extract_images_from_gallery(soup)

                if not article.images:
                    galeria = soup.find('a', id='galerianotas')
                    if galeria:
                        img = galeria.find('img')
                        if img and img.get('src'):
                            img_url = img['src'].replace('/previas/', '/originales/')
                            article.images.append(Image(
                                url=self.config.BASE_URL + img_url,
                                caption=''
                            ))

                # Extract keywords
                keywords_meta = soup.find('meta', {'name': 'keywords'})
                if keywords_meta and keywords_meta.get('content'):
                    article.keywords = [k.strip() for k in keywords_meta['content'].split(',')]

                logger.debug(f"Successfully extracted: {article.title}")

                # Small delay to be respectful
                await asyncio.sleep(self.config.REQUEST_DELAY / self.max_concurrent)

                return article

            except Exception as e:
                logger.error(f"Error extracting {article_url}: {e}", exc_info=True)
                return None

    async def scrape_date(self, date_str: str) -> DailyArticles:
        """Scrape all articles for a specific date using concurrent requests."""
        metadata = ScrapingMetadata(
            date=date_str,
            start_time=datetime.now(timezone.utc).isoformat(),
            proxy_used=self.config.get_proxy_url() is not None
        )

        start_time = datetime.now(timezone.utc)
        logger.info(f"Starting scrape for {date_str}")

        try:
            # Get article URLs
            article_urls = await self.get_article_urls_by_date(date_str)
            metadata.total_articles = len(article_urls)

            if not article_urls:
                logger.warning(f"No articles found for {date_str}")
                return DailyArticles(date=date_str, articles=[], metadata=metadata), None

            # Scrape all articles concurrently
            logger.info(f"Starting concurrent scraping of {len(article_urls)} articles...")

            tasks = [
                self.extract_article_content(url, i+1, len(article_urls))
                for i, url in enumerate(article_urls)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            articles = []
            for result in results:
                if isinstance(result, Exception):
                    metadata.failed_articles += 1
                    metadata.errors.append(str(result))
                elif result is not None:
                    articles.append(result)
                    metadata.successful_articles += 1
                else:
                    metadata.failed_articles += 1

            # Calculate duration
            end_time = datetime.now(timezone.utc)
            metadata.end_time = end_time.isoformat()
            metadata.duration_seconds = (end_time - start_time).total_seconds()

            logger.info(
                f"Completed {date_str}: {metadata.successful_articles}/{metadata.total_articles} articles "
                f"in {metadata.duration_seconds:.2f}s ({metadata.total_articles/metadata.duration_seconds:.1f} articles/sec)"
            )

            daily_articles = DailyArticles(date=date_str, articles=articles, metadata=metadata)

            # Save to JSON file
            if self.save_json:
                self._save_daily_articles(daily_articles)

            # Save to database
            db_result = None
            if self.db and articles:
                db_result = await self.db.bulk_insert_articles(
                    articles,
                    source=Config.SOURCE_NAME
                )
                logger.info(
                    f"Database: {db_result.inserted} new, {db_result.updated} updated"
                )

            return daily_articles, db_result

        except Exception as e:
            logger.critical(f"Critical error scraping {date_str}: {e}", exc_info=True)
            metadata.errors.append(str(e))
            return DailyArticles(date=date_str, articles=[], metadata=metadata), None

    def _save_daily_articles(self, daily_articles: DailyArticles) -> None:
        """Save daily articles and metadata to files."""
        date_str = daily_articles.date.replace('-', '')

        # Save articles
        articles_file = self.config.OUTPUT_DIR / "articles" / f"articles_{date_str}.json"
        daily_articles.save(articles_file)
        logger.info(f"Saved articles to: {articles_file}")

        # Save metadata
        metadata_file = self.config.OUTPUT_DIR / "metadata" / f"metadata_{date_str}.json"
        if daily_articles.metadata:
            daily_articles.metadata.save(metadata_file)
            logger.info(f"Saved metadata to: {metadata_file}")

    async def scrape_date_range(self, start_date: str, end_date: str) -> List[DailyArticles]:
        """Scrape articles across a date range."""
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        all_daily_articles = []
        current = start

        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            daily_articles, _ = await self.scrape_date(date_str)
            all_daily_articles.append(daily_articles)

            current += timedelta(days=1)

        logger.info(f"Completed date range scrape: {start_date} to {end_date}")
        return all_daily_articles
