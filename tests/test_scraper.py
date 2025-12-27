"""
Unit tests for the scraper module.
"""

import pytest
import respx
from httpx import Response

from alcalorscraper.scraper import AlcalorPoliticoScraper
from alcalorscraper.config import Config


class TestAlcalorPoliticoScraper:
    """Tests for AlcalorPoliticoScraper class."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_article_urls_by_date(self, sample_archive_html):
        """Test extraction of article URLs from archive page."""
        # Mock the archive page request
        respx.get(f"{Config.ARCHIVE_URL}?fn=2024-01-01").mock(
            return_value=Response(200, text=sample_archive_html)
        )

        async with AlcalorPoliticoScraper(max_concurrent=1) as scraper:
            urls = await scraper.get_article_urls_by_date("2024-01-01")

        assert len(urls) == 3
        assert "https://www.alcalorpolitico.com/informacion/article-one-111111.html" in urls
        assert "https://www.alcalorpolitico.com/informacion/article-two-222222.html" in urls
        assert "https://www.alcalorpolitico.com/informacion/article-three-333333.html" in urls

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_article_urls_empty(self, empty_archive_html):
        """Test handling of empty archive page."""
        respx.get(f"{Config.ARCHIVE_URL}?fn=2024-01-01").mock(
            return_value=Response(200, text=empty_archive_html)
        )

        async with AlcalorPoliticoScraper(max_concurrent=1) as scraper:
            urls = await scraper.get_article_urls_by_date("2024-01-01")

        assert len(urls) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_article_content(self, sample_article_html):
        """Test extraction of article content from article page."""
        article_url = "https://www.alcalorpolitico.com/informacion/test-article-123456.html"

        respx.get(article_url).mock(
            return_value=Response(200, text=sample_article_html)
        )

        async with AlcalorPoliticoScraper(max_concurrent=1) as scraper:
            article = await scraper.extract_article_content(article_url)

        assert article is not None
        assert article.article_id == "123456"
        assert article.title == "Test Article Title"
        assert article.subtitle == "This is the subtitle"
        # Section includes the prefix from the HTML
        assert "Nacional" in article.section
        assert article.date == "2024-12-15"
        assert "first paragraph" in article.body
        assert "second paragraph" in article.body
        assert len(article.images) == 2
        assert article.keywords == ["test", "article", "politics"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_article_id_from_url(self, sample_article_html):
        """Test article ID extraction from URL."""
        article_url = "https://www.alcalorpolitico.com/informacion/some-long-title-987654.html"

        respx.get(article_url).mock(
            return_value=Response(200, text=sample_article_html)
        )

        async with AlcalorPoliticoScraper(max_concurrent=1) as scraper:
            article = await scraper.extract_article_content(article_url)

        assert article.article_id == "987654"

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_error_handling(self):
        """Test handling of HTTP errors."""
        article_url = "https://www.alcalorpolitico.com/informacion/missing-404.html"

        respx.get(article_url).mock(return_value=Response(404))

        async with AlcalorPoliticoScraper(max_concurrent=1) as scraper:
            article = await scraper.extract_article_content(article_url)

        assert article is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_scrape_date_no_articles(self, empty_archive_html, temp_data_dir, monkeypatch):
        """Test scraping a date with no articles."""
        # Monkeypatch OUTPUT_DIR to use temp directory
        monkeypatch.setattr(Config, "OUTPUT_DIR", temp_data_dir)

        respx.get(f"{Config.ARCHIVE_URL}?fn=2024-01-01").mock(
            return_value=Response(200, text=empty_archive_html)
        )

        async with AlcalorPoliticoScraper(max_concurrent=1) as scraper:
            daily_articles, db_result = await scraper.scrape_date("2024-01-01")

        assert daily_articles.date == "2024-01-01"
        assert len(daily_articles.articles) == 0
        assert daily_articles.metadata.total_articles == 0

    @pytest.mark.asyncio
    async def test_scraper_context_manager(self):
        """Test scraper async context manager."""
        async with AlcalorPoliticoScraper(max_concurrent=5) as scraper:
            assert scraper.client is not None
            assert scraper.max_concurrent == 5

        # Client should be closed after exiting context
        assert scraper.client is None or scraper.client.is_closed


class TestArticleModel:
    """Tests for Article model."""

    def test_article_to_dict(self, sample_article):
        """Test Article.to_dict() method."""
        data = sample_article.to_dict()

        assert data['article_id'] == "123456"
        assert data['title'] == "Test Article Title"
        assert len(data['images']) == 2
        assert data['images'][0]['url'] == "https://example.com/image1.jpg"
        assert data['keywords'] == ["test", "article", "news"]

    def test_article_default_scraped_at(self, sample_article):
        """Test that scraped_at is automatically set."""
        assert sample_article.scraped_at is not None
        # Should be an ISO format timestamp
        assert "T" in sample_article.scraped_at
