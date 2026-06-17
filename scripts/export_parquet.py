#!/usr/bin/env python3
"""
Export USCIS Knowledge Base tables to Parquet files for HuggingFace upload.

Usage:
    python scripts/export_parquet.py [--output-dir huggingface/data]

Exports:
    - uscis_content.parquet        (all content chunks, no HTML)
    - uscis_embeddings.parquet     (embedding vectors as float arrays)
    - processed_urls.parquet
    - scraping_metadata.parquet
    - assessments.parquet
"""

import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

sys.path.insert(0, str(Path(__file__).parent))
from config import config


def export_table(conn, query: str, filename: str, output_dir: Path):
    """Export a SQL query result to Parquet."""
    print(f"  Exporting {filename}...", end=" ", flush=True)
    df = pd.read_sql(query, conn)
    filepath = output_dir / filename
    df.to_parquet(filepath, index=False, engine="pyarrow")
    size_mb = filepath.stat().st_size / (1024 * 1024)
    print(f"✓ {len(df):,} rows ({size_mb:.1f} MB)")
    return len(df)


def export_embeddings(conn, filename: str, output_dir: Path):
    """Export embeddings with vector arrays to Parquet."""
    print(f"  Exporting {filename} (this may take a few minutes)...", flush=True)

    cur = conn.cursor("emb_export")
    cur.execute("""
        SELECT e.id::text, e.content_id::text, e.embedding::text, e.created_at
        FROM uscis_embeddings e
        ORDER BY e.content_id
    """)

    batch_size = 10000
    all_rows = []
    count = 0

    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            emb_id, content_id, embedding_str, created_at = row
            # Parse the pgvector string "[0.1,0.2,...]" to list of floats
            vector = json.loads(embedding_str)
            all_rows.append({
                "id": emb_id,
                "content_id": content_id,
                "embedding": np.array(vector, dtype=np.float32),
                "created_at": created_at,
            })
        count += len(rows)
        print(f"    Read {count:,} rows...", flush=True)

    cur.close()

    df = pd.DataFrame(all_rows)
    filepath = output_dir / filename
    df.to_parquet(filepath, index=False, engine="pyarrow")
    size_mb = filepath.stat().st_size / (1024 * 1024)
    print(f"  ✓ {len(df):,} rows ({size_mb:.1f} MB)")
    return len(df)


def main():
    parser = argparse.ArgumentParser(description="Export USCIS KB to Parquet")
    parser.add_argument("--output-dir", default="huggingface/data", help="Output dir")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to PostgreSQL at {config.postgres.host}:{config.postgres.port}...")
    conn = psycopg2.connect(config.postgres.dsn)

    print(f"Exporting tables to {output_dir}/\n")
    total_rows = 0

    # uscis_content (no HTML — too large and mostly null)
    total_rows += export_table(conn, """
        SELECT id::text, url, title, content, created_at, last_updated,
               immigration_category, document_type, section, source,
               chunk_num, total_chunks
        FROM public.uscis_content
        ORDER BY url, chunk_num
    """, "uscis_content.parquet", output_dir)

    # uscis_embeddings (with full vectors)
    total_rows += export_embeddings(conn, "uscis_embeddings.parquet", output_dir)

    # processed_urls
    total_rows += export_table(conn, """
        SELECT url, processed_at
        FROM public.processed_urls
        ORDER BY processed_at
    """, "processed_urls.parquet", output_dir)

    # scraping_metadata
    total_rows += export_table(conn, """
        SELECT id::text, start_time, end_time, pages_scraped, status, error, created_at
        FROM public.scraping_metadata
        ORDER BY created_at
    """, "scraping_metadata.parquet", output_dir)

    # assessments
    total_rows += export_table(conn, """
        SELECT id::text, created_at, data::text as data_json
        FROM public.assessments
        ORDER BY created_at
    """, "assessments.parquet", output_dir)

    conn.close()
    print(f"\n✅ Export complete! {total_rows:,} total rows → {output_dir}/")


if __name__ == "__main__":
    main()
