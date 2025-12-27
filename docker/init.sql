-- Database initialization for news_scrapers
-- Designed for multi-scraper architecture with unified article storage

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Main articles table (unified for all scrapers)
CREATE TABLE IF NOT EXISTS articles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Source identification (critical for multi-scraper)
    source VARCHAR(50) NOT NULL,
    article_id VARCHAR(50) NOT NULL,

    -- Content
    url TEXT NOT NULL,
    title TEXT,
    subtitle TEXT,
    section VARCHAR(100),
    author VARCHAR(255),
    location TEXT,
    publication_date DATE,
    body TEXT,
    body_html TEXT,

    -- Metadata
    keywords TEXT[],

    -- Scraping metadata
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,

    -- Composite unique constraint for deduplication
    CONSTRAINT unique_source_article UNIQUE (source, article_id)
);

-- Images table (one-to-many relationship)
CREATE TABLE IF NOT EXISTS article_images (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    article_id UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    caption TEXT,
    position INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Scraping runs metadata (for monitoring and debugging)
CREATE TABLE IF NOT EXISTS scrape_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source VARCHAR(50) NOT NULL,
    run_type VARCHAR(20) NOT NULL,
    target_date DATE,
    start_date DATE,
    end_date DATE,

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    total_articles INT DEFAULT 0,
    successful_articles INT DEFAULT 0,
    failed_articles INT DEFAULT 0,
    new_articles INT DEFAULT 0,
    updated_articles INT DEFAULT 0,

    errors JSONB,
    status VARCHAR(20) DEFAULT 'running',

    proxy_used BOOLEAN DEFAULT FALSE,
    duration_seconds FLOAT
);

-- Backfill progress tracking (for resume capability)
CREATE TABLE IF NOT EXISTS backfill_progress (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source VARCHAR(50) NOT NULL,
    last_completed_date DATE NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'in_progress',

    CONSTRAINT unique_source_backfill UNIQUE (source)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_publication_date ON articles(publication_date);
CREATE INDEX IF NOT EXISTS idx_articles_source_date ON articles(source, publication_date);
CREATE INDEX IF NOT EXISTS idx_articles_scraped_at ON articles(scraped_at);
CREATE INDEX IF NOT EXISTS idx_articles_section ON articles(section);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_source_date ON scrape_runs(source, target_date);
CREATE INDEX IF NOT EXISTS idx_article_images_article_id ON article_images(article_id);

-- Full-text search indexes (Spanish language)
CREATE INDEX IF NOT EXISTS idx_articles_title_fts ON articles USING gin(to_tsvector('spanish', COALESCE(title, '')));
CREATE INDEX IF NOT EXISTS idx_articles_body_fts ON articles USING gin(to_tsvector('spanish', COALESCE(body, '')));

-- Trigram indexes for fuzzy search
CREATE INDEX IF NOT EXISTS idx_articles_title_trgm ON articles USING gin(title gin_trgm_ops);
