#!/usr/bin/env python3
"""
USCIS Knowledge Base — Full Ingestion Pipeline (v2)

Reverse-engineered from the Supabase backup schema. This script replicates
the original pipeline that was used to build the USCIS knowledge base.

Pipeline Stages:
    1. DISCOVER  — Find URLs via Firecrawl map/sitemap + SEO seed URLs
    2. SCRAPE    — Crawl pages with Firecrawl (markdown + HTML extraction)
    3. CLASSIFY  — Categorize content (immigration_category, document_type, section)
    4. CHUNK     — Split content into ~1,500 char chunks with overlap
    5. EMBED     — Generate OpenAI text-embedding-ada-002 vectors
    6. STORE_PG  — Store content + embeddings in PostgreSQL/Supabase
    7. STORE_MV  — Ingest embeddings into Milvus for vector search
    8. GRAPH     — Build Neo4j knowledge graph for GraphRAG

Usage:
    # Full pipeline (fresh scrape)
    python scripts/ingest.py --all

    # Individual stages
    python scripts/ingest.py --discover
    python scripts/ingest.py --scrape
    python scripts/ingest.py --chunk
    python scripts/ingest.py --embed
    python scripts/ingest.py --milvus
    python scripts/ingest.py --graph

    # Re-ingest from existing DB snapshot (no scraping)
    python scripts/ingest.py --milvus --graph

Environment:
    Reads from .env file. See .env.example for all variables.

Original Tools Used:
    - Firecrawl (https://github.com/firecrawl/firecrawl) for web scraping
    - OpenAI text-embedding-ada-002 for embeddings (1536 dimensions)
    - Supabase/PostgreSQL + pgvector for storage
    - SEO sitemap parsing for URL discovery
"""

import re
import sys
import uuid
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from config import config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("uscis-ingest")


# ===========================================================================
# STAGE 1 — URL DISCOVERY
# ===========================================================================

def discover_urls() -> list[str]:
    """
    Discover USCIS URLs using Firecrawl's map endpoint + seed URLs.

    The original pipeline used:
    1. Firecrawl /map to discover all URLs on uscis.gov
    2. SEO sitemap parsing (sitemap.xml)
    3. Manual seed URLs for key sections

    Returns list of unique URLs matching the USCIS pattern.
    """
    from firecrawl import Firecrawl

    log.info("=== Stage 1: URL Discovery ===")
    app = Firecrawl(api_key=config.firecrawl.api_key)
    all_urls = set()

    # Map the site to discover URLs
    for seed_url in config.scraping.seed_urls:
        log.info(f"Mapping: {seed_url}")
        try:
            result = app.map(seed_url)
            if result and hasattr(result, 'links'):
                urls = [link.url if hasattr(link, 'url') else link for link in result.links]
            elif isinstance(result, list):
                urls = result
            else:
                urls = []

            # Filter to USCIS domain only
            pattern = re.compile(config.scraping.url_pattern)
            excluded = [re.compile(p) for p in config.scraping.excluded_patterns]
            for url in urls:
                if pattern.match(url) and not any(e.match(url) for e in excluded):
                    all_urls.add(url)

            log.info(f"  Found {len(urls)} URLs, {len(all_urls)} unique total")
        except Exception as e:
            log.warning(f"  Failed to map {seed_url}: {e}")

    log.info(f"Total unique URLs discovered: {len(all_urls)}")

    # Save discovered URLs
    with open("exports/discovered_urls.txt", "w") as f:
        for url in sorted(all_urls):
            f.write(url + "\n")

    return sorted(all_urls)


# ===========================================================================
# STAGE 2 — SCRAPING
# ===========================================================================

def scrape_urls(urls: list[str]) -> list[dict]:
    """
    Scrape URLs using Firecrawl.

    The original pipeline used Firecrawl's scrape endpoint to get:
    - Markdown content (for text extraction)
    - HTML content (for web pages)
    - Page title
    - Metadata

    Uses processed_urls table to skip already-scraped URLs.
    """
    from firecrawl import Firecrawl

    log.info("=== Stage 2: Scraping ===")
    app = Firecrawl(api_key=config.firecrawl.api_key)

    conn = psycopg2.connect(config.postgres.dsn)
    cur = conn.cursor()

    # Get already processed URLs
    cur.execute("SELECT url FROM processed_urls")
    processed = {row[0] for row in cur.fetchall()}
    log.info(f"Already processed: {len(processed)} URLs")

    # Create scraping session
    session_id = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO scraping_metadata (id, start_time, status)
        VALUES (%s, %s, 'running')
    """, (session_id, datetime.now(timezone.utc)))
    conn.commit()

    urls_to_scrape = [u for u in urls if u not in processed]
    log.info(f"URLs to scrape: {len(urls_to_scrape)}")

    results = []
    for url in tqdm(urls_to_scrape[:config.scraping.max_pages], desc="Scraping"):
        try:
            result = app.scrape(url, formats=["markdown", "html"])

            doc = {
                "url": url,
                "title": getattr(result, 'metadata', {}).get('title', '') if hasattr(result, 'metadata') else '',
                "content": result.markdown if hasattr(result, 'markdown') else str(result),
                "html": result.html if hasattr(result, 'html') else None,
            }
            results.append(doc)

            # Mark as processed
            cur.execute("""
                INSERT INTO processed_urls (url, processed_at)
                VALUES (%s, %s)
                ON CONFLICT (url) DO NOTHING
            """, (url, datetime.now(timezone.utc)))
            conn.commit()

        except Exception as e:
            log.warning(f"Failed to scrape {url}: {e}")
            time.sleep(1)

    # Update session
    cur.execute("""
        UPDATE scraping_metadata
        SET end_time = %s, pages_scraped = %s, status = 'completed'
        WHERE id = %s
    """, (datetime.now(timezone.utc), len(results), session_id))
    conn.commit()
    conn.close()

    log.info(f"Scraped {len(results)} pages")
    return results


# ===========================================================================
# STAGE 3 — CLASSIFICATION
# ===========================================================================

# Classification rules reverse-engineered from the data distribution
CATEGORY_RULES = [
    (r"/humanitarian|/refugees|/asylum|/tps|/victims", "Humanitarian"),
    (r"/working-in-the-united-states|/h-1b|/l-1|/e-1|/e-2|/o-1|/tn", "Employment"),
    (r"/green-card|/permanent-residen|/i-485|/i-140|/i-130", "Permanent Residence"),
    (r"/citizenship|/naturalization|/n-400|/civics", "Citizenship"),
    (r"/family|/fiancee|/i-129f|/k-1", "Family"),
]

DOCTYPE_RULES = [
    (r"\.pdf$|/sites/default/files/", "PDF"),
    (r"/policy-manual/", "Policy Manual"),
    (r"/forms/|/i-\d+|/n-\d+|/g-\d+", "Form"),
    (r"/news/|/newsroom/|/press-release", "News"),
    (r"\.(jpg|jpeg|png|gif|svg)$", "Image"),
]


def classify_content(url: str, content: str) -> dict:
    """Classify content by immigration category and document type."""
    url_lower = url.lower()

    # Immigration category
    category = "General"
    for pattern, cat in CATEGORY_RULES:
        if re.search(pattern, url_lower):
            category = cat
            break

    # Document type
    doc_type = "Web Page"
    for pattern, dtype in DOCTYPE_RULES:
        if re.search(pattern, url_lower):
            doc_type = dtype
            break

    # Section — extract from URL path
    parts = url.replace("https://www.uscis.gov/", "").split("/")
    section = parts[0] if parts else "root"

    # Source
    source = "uscis.gov"

    return {
        "immigration_category": category,
        "document_type": doc_type,
        "section": section,
        "source": source,
    }


# ===========================================================================
# STAGE 4 — CHUNKING
# ===========================================================================

def chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> list[str]:
    """
    Split text into chunks of approximately chunk_size characters.

    Strategy (reverse-engineered from data):
    - Target chunk size: ~1,500 chars (avg in DB is 1,426, median 1,372)
    - Max chunk size: 8,000 chars (max in DB is 7,999)
    - Split on paragraph boundaries (\n\n), then sentences
    - Overlap between chunks for context continuity
    """
    chunk_size = chunk_size or config.scraping.chunk_size
    overlap = overlap or config.scraping.chunk_overlap

    if len(text) <= chunk_size:
        return [text]

    # Split into paragraphs
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # If adding this paragraph exceeds max, split
        if len(current_chunk) + len(para) + 2 > config.scraping.max_chunk_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
            # If single paragraph is too long, split by sentences
            if len(para) > config.scraping.max_chunk_size:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                current_chunk = ""
                for sent in sentences:
                    if len(current_chunk) + len(sent) + 1 > chunk_size:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sent
                    else:
                        current_chunk += " " + sent if current_chunk else sent
            else:
                current_chunk = para
        elif len(current_chunk) + len(para) + 2 > chunk_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
                # Add overlap from end of previous chunk
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else ""
                current_chunk = overlap_text + "\n\n" + para if overlap_text else para
            else:
                current_chunk = para
        else:
            current_chunk += "\n\n" + para if current_chunk else para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text]


def process_and_store_content(documents: list[dict]):
    """
    Chunk documents, classify them, and store in PostgreSQL.
    """
    log.info("=== Stage 3+4: Classify & Chunk ===")

    conn = psycopg2.connect(config.postgres.dsn)
    cur = conn.cursor()

    total_chunks = 0
    for doc in tqdm(documents, desc="Processing"):
        url = doc["url"]
        content = doc["content"]
        title = doc.get("title", "")
        html = doc.get("html")

        # Classify
        meta = classify_content(url, content)

        # Chunk
        chunks = chunk_text(content)
        num_chunks = len(chunks)

        for i, chunk in enumerate(chunks, 1):
            chunk_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO uscis_content
                    (id, url, title, content, html, immigration_category,
                     document_type, section, source, chunk_num, total_chunks)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                chunk_id, url, title, chunk,
                html if i == 1 else None,  # Only store HTML for first chunk
                meta["immigration_category"], meta["document_type"],
                meta["section"], meta["source"],
                i, num_chunks,
            ))

        total_chunks += num_chunks

    conn.commit()
    conn.close()
    log.info(f"Stored {total_chunks} chunks from {len(documents)} documents")


# ===========================================================================
# STAGE 5 — EMBEDDINGS (OpenAI)
# ===========================================================================

def generate_embeddings():
    """
    Generate OpenAI embeddings for all content chunks that don't have one yet.

    Model: text-embedding-ada-002 (1536 dimensions)
    Batch size: 100 chunks per API call
    """
    from openai import OpenAI

    log.info("=== Stage 5: Generate Embeddings ===")

    client = OpenAI(api_key=config.openai.api_key)
    conn = psycopg2.connect(config.postgres.dsn)
    cur = conn.cursor()

    # Find content without embeddings
    cur.execute("""
        SELECT c.id, c.content
        FROM uscis_content c
        LEFT JOIN uscis_embeddings e ON e.content_id = c.id
        WHERE e.id IS NULL
        ORDER BY c.url, c.chunk_num
    """)
    rows = cur.fetchall()
    log.info(f"Content chunks needing embeddings: {len(rows)}")

    if not rows:
        log.info("All content already has embeddings!")
        return

    batch_size = config.openai.batch_size
    for i in tqdm(range(0, len(rows), batch_size), desc="Embedding"):
        batch = rows[i:i + batch_size]
        texts = [row[1] for row in batch]
        ids = [row[0] for row in batch]

        try:
            response = client.embeddings.create(
                model=config.openai.embedding_model,
                input=texts,
            )

            for j, embedding_data in enumerate(response.data):
                emb_id = str(uuid.uuid4())
                vector = embedding_data.embedding
                cur.execute("""
                    INSERT INTO uscis_embeddings (id, content_id, embedding)
                    VALUES (%s, %s, %s::vector)
                """, (emb_id, ids[j], str(vector)))

            conn.commit()

        except Exception as e:
            log.error(f"Embedding batch failed: {e}")
            conn.rollback()
            time.sleep(5)

    conn.close()
    log.info("Embedding generation complete")


# ===========================================================================
# STAGE 6 — MILVUS INGESTION
# ===========================================================================

def ingest_milvus():
    """
    Ingest embeddings from PostgreSQL into Milvus for vector search.

    Creates a collection with:
    - id (VARCHAR): content chunk UUID
    - content_id (VARCHAR): link back to uscis_content
    - embedding (FLOAT_VECTOR[1536]): the OpenAI embedding
    - url (VARCHAR): source URL for filtering
    - category (VARCHAR): immigration category for filtering
    - doc_type (VARCHAR): document type for filtering
    """
    from pymilvus import (
        connections, Collection, CollectionSchema,
        FieldSchema, DataType, utility,
    )

    log.info("=== Stage 6: Milvus Ingestion ===")

    # Connect to Milvus
    connections.connect(
        alias="default",
        host=config.milvus.host,
        port=config.milvus.port,
    )
    log.info(f"Connected to Milvus at {config.milvus.host}:{config.milvus.port}")

    collection_name = config.milvus.collection_name

    # Drop existing collection if exists
    if utility.has_collection(collection_name):
        log.info(f"Dropping existing collection: {collection_name}")
        utility.drop_collection(collection_name)

    # Define schema
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=36),
        FieldSchema(name="content_id", dtype=DataType.VARCHAR, max_length=36),
        FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="chunk_num", dtype=DataType.INT32),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=config.milvus.embedding_dim),
    ]
    schema = CollectionSchema(fields, description="USCIS content embeddings")
    collection = Collection(name=collection_name, schema=schema)
    log.info(f"Created collection: {collection_name}")

    # Read from PostgreSQL
    conn = psycopg2.connect(config.postgres.dsn)
    cur = conn.cursor("milvus_cursor")
    cur.execute("""
        SELECT e.id::text, e.content_id::text, c.url,
               c.immigration_category, c.document_type, c.chunk_num,
               e.embedding::text
        FROM uscis_embeddings e
        JOIN uscis_content c ON c.id = e.content_id
        ORDER BY c.url, c.chunk_num
    """)

    batch_size = 1000
    total_inserted = 0

    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            break

        ids = [r[0] for r in rows]
        content_ids = [r[1] for r in rows]
        urls = [r[2][:512] for r in rows]
        categories = [r[3][:64] for r in rows]
        doc_types = [r[4][:64] for r in rows]
        chunk_nums = [r[5] for r in rows]
        embeddings = [json.loads(r[6]) for r in rows]

        collection.insert([
            ids, content_ids, urls, categories, doc_types, chunk_nums, embeddings,
        ])
        total_inserted += len(rows)

        if total_inserted % 10000 == 0:
            log.info(f"  Inserted {total_inserted:,} vectors...")

    cur.close()
    conn.close()

    # Create index for similarity search
    log.info("Creating IVF_FLAT index...")
    index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 256},
    }
    collection.create_index(field_name="embedding", index_params=index_params)
    collection.load()

    log.info(f"✅ Milvus ingestion complete: {total_inserted:,} vectors")


# ===========================================================================
# STAGE 7 — NEO4J KNOWLEDGE GRAPH
# ===========================================================================

def build_knowledge_graph():
    """
    Build a Neo4j knowledge graph from the USCIS content for GraphRAG.

    Graph structure:
    - (:URL {url, title})
    - (:Chunk {id, content, chunk_num, total_chunks})
    - (:Category {name})
    - (:DocumentType {name})
    - (:Section {name})

    Relationships:
    - (URL)-[:HAS_CHUNK]->(Chunk)
    - (Chunk)-[:BELONGS_TO]->(Category)
    - (Chunk)-[:IS_TYPE]->(DocumentType)
    - (Chunk)-[:IN_SECTION]->(Section)
    - (Chunk)-[:NEXT_CHUNK]->(Chunk)  (sequential chunks)
    - (URL)-[:LINKS_TO]->(URL)  (if extractable from content)
    """
    from neo4j import GraphDatabase

    log.info("=== Stage 7: Neo4j Knowledge Graph ===")

    driver = GraphDatabase.driver(
        config.neo4j.uri,
        auth=(config.neo4j.user, config.neo4j.password),
    )
    log.info(f"Connected to Neo4j at {config.neo4j.uri}")

    conn = psycopg2.connect(config.postgres.dsn)
    cur = conn.cursor()

    with driver.session() as session:
        # Clear existing data
        log.info("Clearing existing graph data...")
        session.run("MATCH (n) DETACH DELETE n")

        # Create constraints
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (u:URL) REQUIRE u.url IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (cat:Category) REQUIRE cat.name IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (dt:DocumentType) REQUIRE dt.name IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Section) REQUIRE s.name IS UNIQUE")

        # Create Category nodes
        cur.execute("SELECT DISTINCT immigration_category FROM uscis_content")
        categories = [r[0] for r in cur.fetchall()]
        for cat in categories:
            session.run("MERGE (:Category {name: $name})", name=cat)
        log.info(f"Created {len(categories)} Category nodes")

        # Create DocumentType nodes
        cur.execute("SELECT DISTINCT document_type FROM uscis_content")
        doc_types = [r[0] for r in cur.fetchall()]
        for dt in doc_types:
            session.run("MERGE (:DocumentType {name: $name})", name=dt)
        log.info(f"Created {len(doc_types)} DocumentType nodes")

        # Create Section nodes
        cur.execute("SELECT DISTINCT section FROM uscis_content")
        sections = [r[0] for r in cur.fetchall()]
        for sec in sections:
            session.run("MERGE (:Section {name: $name})", name=sec)
        log.info(f"Created {len(sections)} Section nodes")

        # Create URL and Chunk nodes with relationships (batched)
        cur.execute("""
            SELECT id::text, url, title, left(content, 500) as content_preview,
                   immigration_category, document_type, section,
                   chunk_num, total_chunks
            FROM uscis_content
            ORDER BY url, chunk_num
        """)

        batch_size = 500
        total_chunks = 0
        prev_url = None

        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break

            for row in rows:
                chunk_id, url, title, content_preview, category, doc_type, section, chunk_num, total_chunks_val = row

                # Create/merge URL node
                session.run("""
                    MERGE (u:URL {url: $url})
                    SET u.title = $title
                """, url=url, title=title)

                # Create Chunk node
                session.run("""
                    CREATE (c:Chunk {
                        id: $id,
                        content_preview: $content,
                        chunk_num: $chunk_num,
                        total_chunks: $total_chunks
                    })
                """, id=chunk_id, content=content_preview,
                     chunk_num=chunk_num, total_chunks=total_chunks_val)

                # Relationships
                session.run("""
                    MATCH (u:URL {url: $url}), (c:Chunk {id: $id})
                    CREATE (u)-[:HAS_CHUNK]->(c)
                """, url=url, id=chunk_id)

                session.run("""
                    MATCH (c:Chunk {id: $id}), (cat:Category {name: $cat})
                    CREATE (c)-[:BELONGS_TO]->(cat)
                """, id=chunk_id, cat=category)

                session.run("""
                    MATCH (c:Chunk {id: $id}), (dt:DocumentType {name: $dt})
                    CREATE (c)-[:IS_TYPE]->(dt)
                """, id=chunk_id, dt=doc_type)

                session.run("""
                    MATCH (c:Chunk {id: $id}), (s:Section {name: $sec})
                    CREATE (c)-[:IN_SECTION]->(s)
                """, id=chunk_id, sec=section)

                # Link sequential chunks
                if chunk_num > 1 and url == prev_url:
                    session.run("""
                        MATCH (prev:Chunk)-[:HAS_CHUNK]-(u:URL {url: $url})
                        WHERE prev.chunk_num = $prev_num
                        MATCH (curr:Chunk {id: $curr_id})
                        CREATE (prev)-[:NEXT_CHUNK]->(curr)
                    """, url=url, prev_num=chunk_num - 1, curr_id=chunk_id)

                prev_url = url
                total_chunks += 1

            if total_chunks % 5000 == 0:
                log.info(f"  Processed {total_chunks:,} chunks...")

        # Extract inter-page links from URLs
        log.info("Creating URL cross-references...")
        session.run("""
            MATCH (u1:URL), (u2:URL)
            WHERE u1.url <> u2.url
              AND u1.url STARTS WITH u2.url + '/'
            MERGE (u2)-[:PARENT_OF]->(u1)
        """)

    cur.close()
    conn.close()
    driver.close()

    log.info(f"✅ Neo4j graph complete: {total_chunks:,} chunk nodes")


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="USCIS Knowledge Base Ingestion Pipeline v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/ingest.py --all              # Full pipeline
  python scripts/ingest.py --milvus --graph   # Re-ingest from DB snapshot
  python scripts/ingest.py --embed            # Generate missing embeddings
        """,
    )
    parser.add_argument("--all", action="store_true", help="Run full pipeline")
    parser.add_argument("--discover", action="store_true", help="Stage 1: Discover URLs")
    parser.add_argument("--scrape", action="store_true", help="Stage 2: Scrape URLs")
    parser.add_argument("--chunk", action="store_true", help="Stage 3+4: Classify & chunk")
    parser.add_argument("--embed", action="store_true", help="Stage 5: Generate embeddings")
    parser.add_argument("--milvus", action="store_true", help="Stage 6: Ingest into Milvus")
    parser.add_argument("--graph", action="store_true", help="Stage 7: Build Neo4j graph")
    args = parser.parse_args()

    if not any([args.all, args.discover, args.scrape, args.chunk,
                args.embed, args.milvus, args.graph]):
        parser.print_help()
        return

    log.info("=" * 60)
    log.info("USCIS Knowledge Base — Ingestion Pipeline v2")
    log.info("=" * 60)

    if args.all or args.discover:
        urls = discover_urls()

    if args.all or args.scrape:
        urls = urls if 'urls' in dir() else discover_urls()
        documents = scrape_urls(urls)

    if args.all or args.chunk:
        if 'documents' in dir():
            process_and_store_content(documents)
        else:
            log.warning("No documents to chunk. Run --scrape first or use --all")

    if args.all or args.embed:
        generate_embeddings()

    if args.all or args.milvus:
        ingest_milvus()

    if args.all or args.graph:
        build_knowledge_graph()

    log.info("=" * 60)
    log.info("Pipeline complete!")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
