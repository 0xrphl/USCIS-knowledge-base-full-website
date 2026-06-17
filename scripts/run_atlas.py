#!/usr/bin/env python3
"""
USCIS Knowledge Base — Embedding Atlas Visualization

Loads embeddings from HuggingFace, prepares data,
and launches Apple's Embedding Atlas for interactive exploration.

Usage:
    python scripts/run_atlas.py [--port 8080]

See: https://github.com/apple/embedding-atlas
"""

import os
import sys
import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("atlas")

HF_DATASET = "0xrphl/USCIS-knowledge-base-full-website"
ATLAS_DATA_DIR = "/tmp/atlas_data"


def load_data() -> pd.DataFrame:
    """Load content + embeddings from HuggingFace and merge."""
    cache_path = os.path.join(ATLAS_DATA_DIR, "uscis_merged.parquet")
    os.makedirs(ATLAS_DATA_DIR, exist_ok=True)

    if os.path.exists(cache_path):
        log.info(f"Loading cached merged data from {cache_path}")
        return pd.read_parquet(cache_path)

    log.info("Loading content from HuggingFace...")
    content = pd.read_parquet(f"hf://datasets/{HF_DATASET}/data/uscis_content.parquet")
    log.info(f"  Content: {len(content):,} rows")

    log.info("Loading embeddings from HuggingFace (591 MB)...")
    embeddings = pd.read_parquet(f"hf://datasets/{HF_DATASET}/data/uscis_embeddings.parquet")
    log.info(f"  Embeddings: {len(embeddings):,} rows")

    log.info("Merging...")
    df = content.merge(embeddings[['content_id', 'embedding']], left_on='id', right_on='content_id', how='inner')
    df = df.drop(columns=['content_id'], errors='ignore')
    df['content_preview'] = df['content'].str[:500]

    df.to_parquet(cache_path, index=False)
    log.info(f"  Cached to {cache_path}")
    return df


def run_atlas(df: pd.DataFrame, port: int = 8080):
    """Launch Embedding Atlas using the Python API."""
    log.info(f"Preparing embedding matrix ({len(df):,} × 1536)...")
    emb_matrix = np.stack(df['embedding'].values).astype(np.float32)

    display_df = df[['id', 'url', 'title', 'content_preview', 'immigration_category',
                      'document_type', 'section', 'chunk_num', 'total_chunks']].copy()

    log.info(f"Launching Embedding Atlas on port {port}...")
    log.info(f"  Open http://localhost:{port} in your browser")

    # Use embedding_atlas.show() — the Python API for headless/server mode
    from embedding_atlas import show
    show(display_df, embedding=emb_matrix, port=port, host="0.0.0.0", open_browser=False)


def main():
    parser = argparse.ArgumentParser(description="USCIS Embedding Atlas")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("USCIS Knowledge Base — Embedding Atlas")
    log.info("=" * 60)

    df = load_data()
    run_atlas(df, args.port)


if __name__ == "__main__":
    main()
