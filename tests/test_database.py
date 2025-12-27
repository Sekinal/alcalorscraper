"""
Database integration tests.

These tests require a running PostgreSQL database.
Skip these tests if no database is available.
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from alcalorscraper.database import DatabaseManager, InsertResult, ScrapeRunRecord


class TestDatabaseManager:
    """Tests for DatabaseManager class."""

    @pytest.mark.asyncio
    async def test_database_manager_context_manager(self):
        """Test DatabaseManager async context manager with mock."""
        with patch.object(DatabaseManager, 'connect', new_callable=AsyncMock) as mock_connect:
            with patch.object(DatabaseManager, 'close', new_callable=AsyncMock) as mock_close:
                async with DatabaseManager() as db:
                    mock_connect.assert_called_once()

                mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_insert_result_dataclass(self):
        """Test InsertResult dataclass initialization."""
        result = InsertResult(total=10, inserted=8, updated=2)

        assert result.total == 10
        assert result.inserted == 8
        assert result.updated == 2
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_insert_result_with_errors(self):
        """Test InsertResult with error list."""
        result = InsertResult(
            total=10,
            inserted=5,
            updated=2,
            errors=["Error 1", "Error 2", "Error 3"]
        )

        assert len(result.errors) == 3
        assert "Error 1" in result.errors

    @pytest.mark.asyncio
    async def test_scrape_run_record_dataclass(self):
        """Test ScrapeRunRecord dataclass."""
        run = ScrapeRunRecord(
            source="alcalorpolitico",
            run_type="daily",
            target_date=date(2024, 1, 1),
            total_articles=50,
            successful_articles=48,
            failed_articles=2,
            proxy_used=False,
        )

        assert run.source == "alcalorpolitico"
        assert run.run_type == "daily"
        assert run.target_date == date(2024, 1, 1)
        assert run.new_articles == 0  # Default
        assert run.updated_articles == 0  # Default

    @pytest.mark.asyncio
    async def test_bulk_insert_articles_mock(self, sample_article):
        """Test bulk_insert_articles with mocked database."""
        db = DatabaseManager()

        # Mock the pool and connection
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            'id': 'test-uuid',
            'was_inserted': True
        })
        mock_conn.execute = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_conn),
            __aexit__=AsyncMock(return_value=None)
        ))

        db.pool = mock_pool
        db._connected = True

        result = await db.bulk_insert_articles([sample_article], "alcalorpolitico")

        assert result.total == 1
        assert result.inserted == 1
        assert result.updated == 0
        assert len(result.errors) == 0


class TestDatabaseManagerIntegration:
    """
    Integration tests that require a real database.
    These are skipped if DATABASE_URL is not configured.
    """

    @pytest.fixture
    async def db_manager(self):
        """Create a database manager for testing."""
        db = DatabaseManager()
        try:
            await db.connect()
            yield db
        except Exception:
            pytest.skip("Database not available")
        finally:
            if db._connected:
                await db.close()

    @pytest.mark.asyncio
    async def test_health_check(self, db_manager):
        """Test database health check."""
        result = await db_manager.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_article_count(self, db_manager):
        """Test getting article count."""
        count = await db_manager.get_article_count()
        assert isinstance(count, int)
        assert count >= 0

    @pytest.mark.asyncio
    async def test_get_article_count_by_source(self, db_manager):
        """Test getting article count filtered by source."""
        count = await db_manager.get_article_count("alcalorpolitico")
        assert isinstance(count, int)
        assert count >= 0
