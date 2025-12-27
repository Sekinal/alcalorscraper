"""
Data models for Alcalorpolitico scraper.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pathlib import Path
import json


@dataclass
class Image:
    """Represents an article image."""
    url: str
    caption: str = ""


@dataclass
class Article:
    """Represents a news article."""
    article_id: Optional[str]
    url: str
    title: Optional[str]
    subtitle: Optional[str]
    section: Optional[str]
    source: Optional[str]
    location: Optional[str]
    date: Optional[str]
    body: Optional[str]
    body_html: Optional[str]
    images: List[Image] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['images'] = [{'url': img.url, 'caption': img.caption} for img in self.images]
        return data


@dataclass
class ScrapingMetadata:
    """Metadata for a scraping run."""
    date: str
    start_time: str
    end_time: Optional[str] = None
    total_articles: int = 0
    successful_articles: int = 0
    failed_articles: int = 0
    errors: List[str] = field(default_factory=list)
    proxy_used: bool = False
    duration_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def save(self, output_path: Path) -> None:
        """Save metadata to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)


@dataclass
class DailyArticles:
    """Container for articles scraped on a specific date."""
    date: str
    articles: List[Article] = field(default_factory=list)
    metadata: Optional[ScrapingMetadata] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'date': self.date,
            'total_articles': len(self.articles),
            'articles': [article.to_dict() for article in self.articles],
            'metadata': self.metadata.to_dict() if self.metadata else None
        }

    def save(self, output_path: Path) -> None:
        """Save daily articles to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
