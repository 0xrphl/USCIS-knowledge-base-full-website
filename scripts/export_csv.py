#!/usr/bin/env python3
"""
Export USCIS Knowledge Base tables to CSV files.

Usage:
    python scripts/export_csv.py [--output-dir exports/]

Exports:
    - uscis_content.csv     (without HTML column to reduce size)
    - uscis_embeddings.csv  (id + content_id only — vectors go to Milvus)
    - processed_urls.csv
    - scraping_metadata.csv
    - assessments.csv
    - form_submissions.csv
"""

import os
import sys
import argparse
from pathlib import Path

import pandas as pd
import psycopg2

# Add parent dir to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import config


def export_table(conn, query: str, filename: str, output_dir: Path):
    """Export a SQL query result to CSV."""
    print(f"  Exporting {filename}...", end=" ", flush=True)
    df = pd.read_sql(query, conn)
    filepath = output_dir / filename
    df.to_csv(filepath, index=False)
    size_mb = filepath.stat().st_size / (1024 * 1024)
    print(f"✓ {len(df):,} rows ({size_mb:.1f} MB)")
    return len(df)


def main():
    parser = argparse.ArgumentParser(description="Export USCIS KB tables to CSV")
    parser.add_argument("--output-dir", default="exports", help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to PostgreSQL at {config.postgres.host}:{config.postgres.port}...")
    conn = psycopg2.connect(config.postgres.dsn)

    print(f"Exporting tables to {output_dir}/\n")

    total_rows = 0

    # uscis_content — exclude HTML column (too large, mostly null)
    total_rows += export_table(conn, """
        SELECT id, url, title, content, created_at, last_updated,
               immigration_category, document_type, section, source,
               chunk_num, total_chunks
        FROM public.uscis_content
        ORDER BY url, chunk_num
    """, "uscis_content.csv", output_dir)

    # uscis_embeddings — IDs only (vectors are binary, go to Milvus)
    total_rows += export_table(conn, """
        SELECT id, content_id, created_at
        FROM public.uscis_embeddings
        ORDER BY content_id
    """, "uscis_embeddings_meta.csv", output_dir)

    # processed_urls
    total_rows += export_table(conn, """
        SELECT url, processed_at
        FROM public.processed_urls
        ORDER BY processed_at
    """, "processed_urls.csv", output_dir)

    # scraping_metadata
    total_rows += export_table(conn, """
        SELECT * FROM public.scraping_metadata
        ORDER BY created_at
    """, "scraping_metadata.csv", output_dir)

    # assessments
    total_rows += export_table(conn, """
        SELECT id, created_at, data::text as data_json
        FROM public.assessments
        ORDER BY created_at
    """, "assessments.csv", output_dir)

    # form_submissions
    total_rows += export_table(conn, """
        SELECT id, created_at, updated_at, user_id, form_type, status, data::text as data_json
        FROM public.form_submissions
        ORDER BY created_at
    """, "form_submissions.csv", output_dir)

    conn.close()
    print(f"\n✅ Export complete! {total_rows:,} total rows exported to {output_dir}/")


if __name__ == "__main__":
    main()
