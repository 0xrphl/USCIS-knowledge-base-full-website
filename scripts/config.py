"""
Configuration loader for USCIS Knowledge Base pipeline.
Reads from .env file or environment variables.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed, use env vars directly


@dataclass
class PostgresConfig:
    host: str = field(default_factory=lambda: os.getenv("PG_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("PG_PORT", "5432")))
    database: str = field(default_factory=lambda: os.getenv("PG_DATABASE", "postgres"))
    user: str = field(default_factory=lambda: os.getenv("PG_USER", "postgres"))
    password: str = field(default_factory=lambda: os.getenv("PG_PASSWORD", "postgres"))

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class OpenAIConfig:
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    embedding_model: str = field(default_factory=lambda: os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002"))
    embedding_dimensions: int = 1536
    batch_size: int = field(default_factory=lambda: int(os.getenv("OPENAI_BATCH_SIZE", "100")))


@dataclass
class FirecrawlConfig:
    api_key: str = field(default_factory=lambda: os.getenv("FIRECRAWL_API_KEY", ""))
    api_url: str = field(default_factory=lambda: os.getenv("FIRECRAWL_API_URL", "https://api.firecrawl.dev"))


@dataclass
class MilvusConfig:
    host: str = field(default_factory=lambda: os.getenv("MILVUS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("MILVUS_PORT", "19530")))
    collection_name: str = field(default_factory=lambda: os.getenv("MILVUS_COLLECTION", "uscis_embeddings"))
    embedding_dim: int = 1536


@dataclass
class Neo4jConfig:
    uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", "neo4jpassword"))


@dataclass
class ScrapingConfig:
    """Configuration for the scraping pipeline."""
    seed_urls: list = field(default_factory=lambda: [
        "https://www.uscis.gov",
        "https://www.uscis.gov/sitemap.xml",
        "https://www.uscis.gov/forms/all-forms",
        "https://www.uscis.gov/policy-manual",
        "https://www.uscis.gov/newsroom",
        "https://www.uscis.gov/green-card",
        "https://www.uscis.gov/citizenship",
        "https://www.uscis.gov/working-in-the-united-states",
        "https://www.uscis.gov/humanitarian",
        "https://www.uscis.gov/family",
    ])
    max_pages: int = field(default_factory=lambda: int(os.getenv("MAX_PAGES", "10000")))
    chunk_size: int = field(default_factory=lambda: int(os.getenv("CHUNK_SIZE", "1500")))
    chunk_overlap: int = field(default_factory=lambda: int(os.getenv("CHUNK_OVERLAP", "200")))
    max_chunk_size: int = field(default_factory=lambda: int(os.getenv("MAX_CHUNK_SIZE", "8000")))
    url_pattern: str = r"https://www\.uscis\.gov/.*"
    excluded_patterns: list = field(default_factory=lambda: [
        r".*\.(jpg|jpeg|png|gif|svg|ico|css|js)$",
        r".*/search\?.*",
        r".*/print/.*",
    ])


@dataclass
class Config:
    postgres: PostgresConfig = field(default_factory=PostgresConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    firecrawl: FirecrawlConfig = field(default_factory=FirecrawlConfig)
    milvus: MilvusConfig = field(default_factory=MilvusConfig)
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)


# Singleton
config = Config()
