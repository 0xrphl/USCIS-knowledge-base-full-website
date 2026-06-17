#!/usr/bin/env python3
"""
USCIS Knowledge Base — Embedding Atlas Visualization

Patches the interactive prompt to auto-select the embedding column,
then launches the embedding-atlas CLI server.
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


def load_data() -> str:
    """Load content + embeddings, merge, save as parquet for CLI."""
    os.makedirs(ATLAS_DATA_DIR, exist_ok=True)
    output_path = os.path.join(ATLAS_DATA_DIR, "uscis_atlas.parquet")

    if os.path.exists(output_path):
        log.info(f"Atlas data already prepared at {output_path}")
        return output_path

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

    atlas_df = df[['id', 'url', 'title', 'content_preview', 'immigration_category',
                    'document_type', 'section', 'chunk_num', 'total_chunks', 'embedding']].copy()

    atlas_df.to_parquet(output_path, index=False)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    log.info(f"✅ Saved to {output_path} ({size_mb:.1f} MB)")
    return output_path


def run_atlas(data_path: str, port: int = 8080):
    """Launch embedding-atlas by monkey-patching the interactive prompt."""
    log.info(f"Launching Embedding Atlas on port {port}...")
    log.info(f"  Open http://localhost:{port} in your browser")

    # Monkey-patch inquirer.prompt to auto-select "embedding" column
    import inquirer
    original_prompt = inquirer.prompt

    def patched_prompt(questions, *args, **kwargs):
        """Auto-answer the column selection prompt."""
        results = {}
        for q in questions:
            if hasattr(q, 'name'):
                # Auto-select "embedding" for any question
                results[q.name] = "embedding"
                log.info(f"  Auto-selected column: embedding")
        return results

    inquirer.prompt = patched_prompt

    # Now import and run the CLI main function directly
    from embedding_atlas.cli import main as atlas_main
    sys.argv = [
        "embedding-atlas",
        data_path,
        "--port", str(port),
        "--host", "0.0.0.0",
    ]
    log.info(f"  Starting atlas server...")
    atlas_main(standalone_mode=False)


def main():
    parser = argparse.ArgumentParser(description="USCIS Embedding Atlas")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("USCIS Knowledge Base — Embedding Atlas")
    log.info("=" * 60)

    data_path = load_data()
    run_atlas(data_path, args.port)


if __name__ == "__main__":
    main()
