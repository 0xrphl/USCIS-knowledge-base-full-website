#!/usr/bin/env python3
"""
USCIS Knowledge Base — Embedding Atlas Visualization

Loads embeddings from HuggingFace, runs UMAP dimension reduction,
and launches Apple's Embedding Atlas for interactive exploration.

Usage:
    # Launch interactive visualization (opens browser)
    python scripts/run_atlas.py

    # Export UMAP projections to parquet (for HuggingFace upload)
    python scripts/run_atlas.py --export

    # Specify custom port
    python scripts/run_atlas.py --port 8080

Requirements:
    pip install embedding-atlas pandas pyarrow numpy

See: https://github.com/apple/embedding-atlas
"""

import sys
import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("atlas")

HF_DATASET = "0xrphl/USCIS-knowledge-base-full-website"


def load_data() -> pd.DataFrame:
    """Load content + embeddings from HuggingFace and merge into a single DataFrame."""
    log.info("Loading content from HuggingFace...")
    content = pd.read_parquet(f"hf://datasets/{HF_DATASET}/data/uscis_content.parquet")
    log.info(f"  Content: {len(content):,} rows")

    log.info("Loading embeddings from HuggingFace (591 MB)...")
    embeddings = pd.read_parquet(f"hf://datasets/{HF_DATASET}/data/uscis_embeddings.parquet")
    log.info(f"  Embeddings: {len(embeddings):,} rows")

    # Merge on content_id = id
    log.info("Merging content + embeddings...")
    df = content.merge(embeddings[['content_id', 'embedding']], left_on='id', right_on='content_id', how='inner')
    df = df.drop(columns=['content_id'], errors='ignore')

    # Truncate content for display
    df['content_preview'] = df['content'].str[:300]

    log.info(f"  Merged: {len(df):,} rows with embeddings")
    return df


def extract_embedding_matrix(df: pd.DataFrame) -> np.ndarray:
    """Extract the embedding column into a numpy matrix."""
    log.info("Extracting embedding matrix...")
    embeddings = np.stack(df['embedding'].values)
    log.info(f"  Matrix shape: {embeddings.shape}")
    return embeddings


def export_projections(df: pd.DataFrame, output_path: str = "huggingface/data/uscis_umap_projections.parquet"):
    """Run UMAP and export 2D projections to parquet."""
    from umap import UMAP

    embeddings = extract_embedding_matrix(df)

    log.info("Running UMAP dimension reduction (1536 → 2D)...")
    reducer = UMAP(n_components=2, n_neighbors=15, min_dist=0.1, metric='cosine', random_state=42, verbose=True)
    projections = reducer.fit_transform(embeddings)
    log.info(f"  UMAP complete: {projections.shape}")

    # Build export DataFrame
    export_df = df[['id', 'url', 'title', 'immigration_category', 'document_type',
                     'section', 'chunk_num', 'total_chunks', 'content_preview']].copy()
    export_df['umap_x'] = projections[:, 0]
    export_df['umap_y'] = projections[:, 1]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    export_df.to_parquet(output_path, index=False)
    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    log.info(f"✅ Exported {len(export_df):,} projections to {output_path} ({size_mb:.1f} MB)")

    return export_df


def run_atlas(df: pd.DataFrame, port: int = 8080):
    """Launch Embedding Atlas interactive visualization."""
    from embedding_atlas import EmbeddingAtlas

    embeddings = extract_embedding_matrix(df)

    # Prepare the display DataFrame (drop the raw embedding column for Atlas)
    display_df = df[['id', 'url', 'title', 'content_preview', 'immigration_category',
                      'document_type', 'section', 'chunk_num', 'total_chunks']].copy()

    log.info(f"Launching Embedding Atlas on port {port}...")
    log.info(f"  Open http://localhost:{port} in your browser")

    atlas = EmbeddingAtlas(display_df, embeddings=embeddings)
    atlas.serve(port=port)


def main():
    parser = argparse.ArgumentParser(description="USCIS Embedding Atlas Visualization")
    parser.add_argument("--export", action="store_true", help="Export UMAP projections to parquet")
    parser.add_argument("--port", type=int, default=8080, help="Atlas server port (default: 8080)")
    parser.add_argument("--output", default="huggingface/data/uscis_umap_projections.parquet",
                        help="Output path for UMAP projections")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("USCIS Knowledge Base — Embedding Atlas")
    log.info("=" * 60)

    df = load_data()

    if args.export:
        export_projections(df, args.output)
    else:
        run_atlas(df, args.port)


if __name__ == "__main__":
    main()
