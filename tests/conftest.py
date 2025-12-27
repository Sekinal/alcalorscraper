"""
Pytest fixtures for alcalorscraper tests.
"""

import pytest
from datetime import datetime
from pathlib import Path

from alcalorscraper.models import Article, Image


@pytest.fixture
def sample_article():
    """Sample Article object for testing."""
    return Article(
        article_id="123456",
        url="https://www.alcalorpolitico.com/informacion/test-article-123456.html",
        title="Test Article Title",
        subtitle="Test Subtitle",
        section="Nacional",
        source="Test Agency",
        location="Veracruz, Mexico 01/01/2024",
        date="2024-01-01",
        body="This is the test article body content.",
        body_html="<div>This is the test article body content.</div>",
        images=[
            Image(url="https://example.com/image1.jpg", caption="Image 1"),
            Image(url="https://example.com/image2.jpg", caption="Image 2"),
        ],
        keywords=["test", "article", "news"],
    )


@pytest.fixture
def sample_archive_html():
    """Sample archive page HTML for testing URL extraction."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Archivo de Noticias</title></head>
    <body>
        <div class="contenido">
            <a href="/informacion/article-one-111111.html">Article One</a>
            <a href="/informacion/article-two-222222.html">Article Two</a>
            <a href="/informacion/article-three-333333.html">Article Three</a>
            <a href="/other-section/not-an-article.html">Not an article</a>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def sample_article_html():
    """Sample article page HTML for testing content extraction."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="keywords" content="test, article, politics">
        <title>Test Article</title>
    </head>
    <body>
        <div id="areasuperiorColumna">
            <p id="seccion">Sección: Nacional</p>
            <h1>Test Article Title</h1>
            <h2>This is the subtitle</h2>
            <h3>
                Test News Agency
                <span id="lugar">Veracruz, Mexico 15/12/2024</span>
            </h3>
        </div>
        <div class="cuerponota">
            <p>This is the first paragraph of the article.</p>
            <p>This is the second paragraph with more details.</p>
        </div>
        <script>
            $.iLightBox([
                { URL: "/images/originales/photo1.jpg", caption: "Photo caption 1" },
                { URL: "/images/originales/photo2.jpg", caption: "Photo caption 2" }
            ]);
        </script>
    </body>
    </html>
    """


@pytest.fixture
def empty_archive_html():
    """Empty archive page HTML for testing no articles scenario."""
    return """
    <!DOCTYPE html>
    <html>
    <body>
        <div class="contenido">
            <p>No hay noticias para esta fecha.</p>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create temporary data directory structure."""
    data_dir = tmp_path / "data"
    (data_dir / "articles").mkdir(parents=True)
    (data_dir / "metadata").mkdir(parents=True)
    (data_dir / "logs").mkdir(parents=True)
    return data_dir
