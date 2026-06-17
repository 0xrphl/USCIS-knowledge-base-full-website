#!/usr/bin/env python3
"""
Load USCIS Knowledge Base from HuggingFace into PostgreSQL.

Downloads parquet files from the HuggingFace dataset and loads them
into a local PostgreSQL instance with pgvector.

Usage:
    python scripts/load_from_huggingface.py

Environment:
    PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE (see .env)
"""

import sys
import json
import time
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).parent))
from config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("hf-loader")

HF_DATASET = "0xrphl/USCIS-knowledge-base-full-website"


def wait_for_postgres(max_retries=30, delay=2):
    """Wait for PostgreSQL to be ready."""
    for i in range(max_retries):
        try:
            conn = psycopg2.connect(config.postgres.dsn)
            conn.close()
            log.info("PostgreSQL is ready!")
            return True
        except psycopg2.OperationalError:
            log.info(f"Waiting for PostgreSQL... ({i+1}/{max_retries})")
            time.sleep(delay)
    raise RuntimeError("PostgreSQL not available after max retries")


def create_schema(conn):
    """Create tables if they don't exist."""
    cur = conn.cursor()

    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    cur.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS uscis_content (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            url TEXT NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            immigration_category TEXT,
            document_type TEXT,
            section TEXT,
            source TEXT,
            chunk_num INTEGER DEFAULT 1,
            total_chunks INTEGER DEFAULT 1
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS uscis_embeddings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            content_id UUID REFERENCES uscis_content(id),
            embedding vector(1536),
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS processed_urls (
            url TEXT PRIMARY KEY,
            processed_at TIMESTAMPTZ NOT NULL
        );
    """)

    conn.commit()
    log.info("Schema created/verified")


def check_if_loaded(conn) -> bool:
    """Check if data is already loaded."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT count(*) FROM uscis_content")
        count = cur.fetchone()[0]
        if count > 0:
            log.info(f"Data already loaded: {count:,} content rows. Skipping.")
            return True
    except psycopg2.errors.UndefinedTable:
        conn.rollback()
    return False


def load_content(conn):
    """Load uscis_content from HuggingFace parquet."""
    log.info("Downloading uscis_content.parquet from HuggingFace...")
    url = f"hf://datasets/{HF_DATASET}/data/uscis_content.parquet"
    df = pd.read_parquet(url)
    log.info(f"Downloaded {len(df):,} content rows")

    cur = conn.cursor()
    batch_size = 1000
    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i+batch_size]
        values = []
        for _, row in batch.iterrows():
            values.append((
                row['id'], row['url'], row.get('title'), row['content'],
                row.get('created_at'), row.get('last_updated'),
                row.get('immigration_category'), row.get('document_type'),
                row.get('section'), row.get('source'),
                int(row.get('chunk_num', 1)), int(row.get('total_chunks', 1)),
            ))
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO uscis_content (id, url, title, content, created_at, last_updated,
                immigration_category, document_type, section, source, chunk_num, total_chunks)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, values)
        conn.commit()
        if (i + batch_size) % 10000 == 0 or i + batch_size >= len(df):
            log.info(f"  Loaded {min(i+batch_size, len(df)):,}/{len(df):,} content rows")

    log.info(f"✅ Loaded {len(df):,} content rows")


def load_embeddings(conn):
    """Load uscis_embeddings from HuggingFace parquet."""
    log.info("Downloading uscis_embeddings.parquet from HuggingFace (591 MB)...")
    url = f"hf://datasets/{HF_DATASET}/data/uscis_embeddings.parquet"
    df = pd.read_parquet(url)
    log.info(f"Downloaded {len(df):,} embedding rows")

    cur = conn.cursor()
    batch_size = 500
    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i+batch_size]
        values = []
        for _, row in batch.iterrows():
            emb = row['embedding']
            if isinstance(emb, np.ndarray):
                emb_str = str(emb.tolist())
            elif isinstance(emb, list):
                emb_str = str(emb)
            else:
                emb_str = str(emb)
            values.append((row['id'], row['content_id'], emb_str, row.get('created_at')))

        psycopg2.extras.execute_batch(cur, """
            INSERT INTO uscis_embeddings (id, content_id, embedding, created_at)
            VALUES (%s, %s, %s::vector, %s)
            ON CONFLICT (id) DO NOTHING
        """, values)
        conn.commit()
        if (i + batch_size) % 10000 == 0 or i + batch_size >= len(df):
            log.info(f"  Loaded {min(i+batch_size, len(df)):,}/{len(df):,} embedding rows")

    log.info(f"✅ Loaded {len(df):,} embedding rows")


def load_urls(conn):
    """Load processed_urls from HuggingFace parquet."""
    log.info("Downloading processed_urls.parquet from HuggingFace...")
    url = f"hf://datasets/{HF_DATASET}/data/processed_urls.parquet"
    df = pd.read_parquet(url)

    cur = conn.cursor()
    values = [(row['url'], row['processed_at']) for _, row in df.iterrows()]
    psycopg2.extras.execute_batch(cur, """
        INSERT INTO processed_urls (url, processed_at)
        VALUES (%s, %s)
        ON CONFLICT (url) DO NOTHING
    """, values)
    conn.commit()
    log.info(f"✅ Loaded {len(df):,} processed URLs")


def main():
    log.info("=" * 60)
    log.info("USCIS Knowledge Base — HuggingFace Data Loader")
    log.info("=" * 60)

    wait_for_postgres()
    conn = psycopg2.connect(config.postgres.dsn)

    create_schema(conn)

    if check_if_loaded(conn):
        conn.close()
        return

    load_content(conn)
    load_embeddings(conn)
    load_urls(conn)

    # Verify
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM uscis_content")
    content_count = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM uscis_embeddings")
    emb_count = cur.fetchone()[0]

    conn.close()

    log.info("=" * 60)
    log.info(f"✅ Load complete! {content_count:,} content + {emb_count:,} embeddings")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
