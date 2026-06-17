#!/usr/bin/env python3
"""
USCIS Knowledge Base — Embedding Atlas Visualization

Loads embeddings from HuggingFace, prepares a combined dataset,
and launches Apple's Embedding Atlas CLI for interactive exploration.

Usage:
    # Launch interactive visualization (opens browser on port 8080)
    python scripts/run_atlas.py

    # Specify custom port
    python scripts/run_atlas.py --port 8080

Requirements:
    pip install embedding-atlas pandas pyarrow numpy

See: https://github.com/apple/embedding-atlas
"""

import os
import sys
import subprocess
import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("atlas")

HF_DATASET = "0xrphl/USCIS-knowledge-base-full-website"
ATLAS_DATA_DIR = "/tmp/atlas_data"


def load_and_prepare_data() -> str:
    """
    Load content + embeddings from HuggingFace, merge them,
    and save as a parquet file for embedding-atlas CLI.
    """
    os.makedirs(ATLAS_DATA_DIR, exist_ok=True)
    output_path = os.path.join(ATLAS_DATA_DIR, "uscis_atlas.parquet")

    # Skip if already prepared
    if os.path.exists(output_path):
        log.info(f"Atlas data already prepared at {output_path}")
        return output_path

    log.info("Loading content from HuggingFace...")
    content = pd.read_parquet(f"hf://datasets/{HF_DATASET}/data/uscis_content.parquet")
    log.info(f"  Content: {len(content):,} rows")

    log.info("Loading embeddings from HuggingFace (591 MB — this takes a few minutes)...")
    embeddings = pd.read_parquet(f"hf://datasets/{HF_DATASET}/data/uscis_embeddings.parquet")
    log.info(f"  Embeddings: {len(embeddings):,} rows")

    # Merge on content_id = id
    log.info("Merging content + embeddings...")
    df = content.merge(
        embeddings[['content_id', 'embedding']],
        left_on='id', right_on='content_id', how='inner'
    )
    df = df.drop(columns=['content_id'], errors='ignore')

    # Truncate content for display (Atlas shows this in hover)
    df['content_preview'] = df['content'].str[:500]

    # Extract embedding dimensions into separate columns (embedding_0, embedding_1, ...)
    log.info("Expanding embedding vectors into columns...")
    emb_matrix = np.stack(df['embedding'].values)
    emb_cols = [f"embedding_{i}" for i in range(emb_matrix.shape[1])]
    emb_df = pd.DataFrame(emb_matrix, columns=emb_cols, index=df.index)

    # Build final DataFrame for Atlas
    atlas_df = pd.concat([
        df[['id', 'url', 'title', 'content_preview', 'immigration_category',
            'document_type', 'section', 'chunk_num', 'total_chunks']],
        emb_df
    ], axis=1)

    log.info(f"Saving atlas dataset ({len(atlas_df):,} rows)...")
    atlas_df.to_parquet(output_path, index=False)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    log.info(f"✅ Saved to {output_path} ({size_mb:.1f} MB)")

    return output_path


def run_atlas(data_path: str, port: int = 8080):
    """Launch embedding-atlas CLI on the prepared data."""
    log.info(f"Launching Embedding Atlas on port {port}...")
    log.info(f"  Data: {data_path}")
    log.info(f"  Open http://localhost:{port} in your browser")

    # embedding-atlas CLI: embedding-atlas <file> --port <port> --host 0.0.0.0
    cmd = [
        "embedding-atlas", data_path,
        "--port", str(port),
        "--host", "0.0.0.0",
    ]

    log.info(f"  Command: {' '.join(cmd)}")

    # Run as subprocess (blocks until killed)
    proc = subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description="USCIS Embedding Atlas Visualization")
    parser.add_argument("--port", type=int, default=8080, help="Atlas server port (default: 8080)")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("USCIS Knowledge Base — Embedding Atlas")
    log.info("=" * 60)

    data_path = load_and_prepare_data()
    run_atlas(data_path, args.port)


if __name__ == "__main__":
    main()
