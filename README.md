<p align="center">
  <img src="uscis-knowledge-base-banner.svg" alt="USCIS Knowledge Base Banner" width="100%"/>
</p>

# 🇺🇸 USCIS Knowledge Base

A comprehensive knowledge base of **99,489 content chunks** from **4,666 USCIS pages** with **OpenAI embeddings** (1536-dim), ready for RAG (Retrieval-Augmented Generation), semantic search, and GraphRAG applications.

[![Data Quality](https://img.shields.io/badge/data_quality-99.99%25-brightgreen)](reports/DATA_AUDIT.md)
[![Content Chunks](https://img.shields.io/badge/chunks-99%2C489-blue)]()
[![Embeddings](https://img.shields.io/badge/embeddings-99%2C488-blue)]()
[![URLs](https://img.shields.io/badge/URLs-4%2C666-blue)]()
[![HuggingFace Dataset](https://img.shields.io/badge/🤗_HuggingFace-Dataset-yellow)](https://huggingface.co/datasets/0xrphl/USCIS-knowledge-base-full-website)
[![Firecrawl](https://img.shields.io/badge/🔥_Firecrawl-Scraping-orange)](https://github.com/firecrawl/firecrawl)

---

## 📋 Overview

This dataset was built by scraping the entire [USCIS website](https://www.uscis.gov) using [Firecrawl](https://github.com/firecrawl/firecrawl), chunking the content, classifying it by immigration category, and generating OpenAI `text-embedding-ada-002` embeddings.

### Data Breakdown

| Document Type | Chunks | % |
|---|---|---|
| PDF | 55,957 | 56.2% |
| Web Page | 32,625 | 32.8% |
| Policy Manual | 8,886 | 8.9% |
| Form | 1,156 | 1.2% |
| News | 800 | 0.8% |
| Image | 65 | 0.1% |

| Immigration Category | Chunks | % |
|---|---|---|
| General | 92,520 | 93.0% |
| Humanitarian | 2,488 | 2.5% |
| Employment | 2,219 | 2.2% |
| Permanent Residence | 1,553 | 1.6% |
| Citizenship | 573 | 0.6% |
| Family | 136 | 0.1% |

---

## 📦 Get the Dataset

The full dataset (content + embeddings) is hosted on 🤗 HuggingFace:

📦 **[huggingface.co/datasets/0xrphl/USCIS-knowledge-base-full-website](https://huggingface.co/datasets/0xrphl/USCIS-knowledge-base-full-website)**

### Load with 🤗 Datasets

```python
from datasets import load_dataset

# Load content chunks (99,489 rows)
content = load_dataset("0xrphl/USCIS-knowledge-base-full-website", "content", split="train")
print(content[0])

# Load embeddings (99,488 rows × 1536-dim float32 vectors)
embeddings = load_dataset("0xrphl/USCIS-knowledge-base-full-website", "embeddings", split="train")
print(len(embeddings[0]["embedding"]))  # 1536
```

### Load with Pandas

```python
import pandas as pd

content = pd.read_parquet("hf://datasets/0xrphl/USCIS-knowledge-base-full-website/data/uscis_content.parquet")
embeddings = pd.read_parquet("hf://datasets/0xrphl/USCIS-knowledge-base-full-website/data/uscis_embeddings.parquet")
```

### Available Files on HuggingFace

| File | Rows | Size | Description |
|---|---|---|---|
| `uscis_content.parquet` | 99,489 | 47 MB | Content chunks with metadata |
| `uscis_embeddings.parquet` | 99,488 | 591 MB | OpenAI embedding vectors |
| `processed_urls.parquet` | 4,666 | 0.2 MB | All scraped URLs |
| `scraping_metadata.parquet` | 28 | <1 KB | Scraping session logs |
| `assessments.parquet` | 5 | <1 KB | Immigration assessments |

---

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Firecrawl   │────▶│  PostgreSQL   │────▶│   Milvus    │
│  (Scraping)  │     │  + pgvector   │     │  (Vectors)  │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
                     ┌─────▼───────┐
                     │   Neo4j     │
                     │  (GraphRAG) │
                     └─────────────┘
```

| Service | Port | Web UI | Credentials |
|---|---|---|---|
| **PostgreSQL** | `5432` | — | `postgres` / `postgres` |
| **pgAdmin** | `5050` | [localhost:5050](http://127.0.0.1:5050) | `admin@admin.com` / `admin` |
| **Milvus** | `19530` | — | — |
| **Attu** (Milvus UI) | `3000` | [localhost:3000](http://localhost:3000) | — |
| **Neo4j** | `7474` / `7687` | [localhost:7474](http://localhost:7474) | `neo4j` / `neo4jpassword` |
| **MinIO** | `9001` | [localhost:9001](http://localhost:9001) | `minioadmin` / `minioadmin` |

---

## 🚀 Quick Start

### 1. Start Infrastructure

```bash
git clone https://github.com/0xrphl/USCIS-knowledge-base-full-website.git
cd USCIS-knowledge-base-full-website

cp .env.example .env
# Edit .env with your API keys (OpenAI, Firecrawl)

docker compose up -d
```

### 2. Ingest Data into Milvus & Neo4j

```bash
pip install -r scripts/requirements.txt

# Ingest from HuggingFace into local Milvus + Neo4j
python scripts/ingest.py --milvus --graph
```

### 3. Browse the Data

- **pgAdmin**: http://127.0.0.1:5050
- **Neo4j Browser**: http://localhost:7474
- **Attu (Milvus)**: http://localhost:3000

---

## 🔧 Ingestion Pipeline

The `scripts/ingest.py` script is the full scraping and ingestion pipeline built with [Firecrawl](https://github.com/firecrawl/firecrawl). It supports 7 stages:

| Stage | Command | Description |
|---|---|---|
| 1. Discover | `--discover` | Find URLs via [Firecrawl](https://github.com/firecrawl/firecrawl) map + SEO sitemaps |
| 2. Scrape | `--scrape` | Crawl pages with [Firecrawl](https://github.com/firecrawl/firecrawl) (markdown + HTML) |
| 3+4. Classify & Chunk | `--chunk` | Categorize content + split into ~1,500 char chunks |
| 5. Embed | `--embed` | Generate OpenAI text-embedding-ada-002 vectors |
| 6. Milvus | `--milvus` | Ingest vectors into Milvus for similarity search |
| 7. Graph | `--graph` | Build Neo4j knowledge graph for GraphRAG |

```bash
# Full pipeline (fresh scrape — requires Firecrawl + OpenAI API keys)
python scripts/ingest.py --all

# Re-ingest from HuggingFace data into Milvus/Neo4j (no API keys needed)
python scripts/ingest.py --milvus --graph

# Generate missing embeddings only
python scripts/ingest.py --embed
```

### Tools Used
- **[Firecrawl](https://github.com/firecrawl/firecrawl)** — Web scraping and URL discovery
- **OpenAI `text-embedding-ada-002`** — 1536-dimensional embeddings
- **PostgreSQL + pgvector** — Primary storage
- **Milvus** — Vector similarity search
- **Neo4j** — Knowledge graph for GraphRAG

---

## 📁 Project Structure

```
.
├── docker-compose.yml              # PG + pgAdmin + Milvus + Neo4j
├── .env.example                    # Environment template
├── README.md
├── uscis-knowledge-base-banner.svg # Repo banner
│
├── scripts/                        # Python pipeline
│   ├── config.py                   # Environment config loader
│   ├── requirements.txt            # Python dependencies
│   └── ingest.py                   # Full Firecrawl ingestion pipeline
│
└── reports/                        # Data documentation
    ├── DATA_AUDIT.md               # Full data quality report
    ├── INGESTION_ERRORS.md         # Error analysis
    └── SCHEMA.md                   # Database schema docs
```

---

## 📊 Data Quality

See [reports/DATA_AUDIT.md](reports/DATA_AUDIT.md) for the full report.

| Check | Status | Score |
|---|---|---|
| All URLs have content | ✅ Pass | 100% |
| All content has embeddings | ⚠️ 1 missing | 99.999% |
| No null required fields | ✅ Pass | 100% |
| Chunk sequence integrity | ⚠️ 1 URL with gaps | 99.98% |
| **Overall** | **✅ Excellent** | **99.99%** |

---

## 🗺️ Roadmap

- [x] Scrape 4,666 USCIS pages with [Firecrawl](https://github.com/firecrawl/firecrawl)
- [x] Chunk content (~1,500 chars, 99,489 chunks)
- [x] Generate OpenAI embeddings (99,488/99,489)
- [x] Upload dataset to [HuggingFace](https://huggingface.co/datasets/0xrphl/USCIS-knowledge-base-full-website)
- [x] Data audit and quality reports
- [x] Firecrawl ingestion pipeline
- [ ] Milvus vector ingestion from HuggingFace
- [ ] Neo4j GraphRAG knowledge graph
- [ ] Semantic search API
- [ ] RAG chatbot demo
- [ ] Incremental re-scraping (delta updates)
- [ ] Multi-language support (Spanish translations)

---

## 📄 License

Data sourced from [USCIS.gov](https://www.uscis.gov) (U.S. government public domain).  
Scraped with [Firecrawl](https://github.com/firecrawl/firecrawl).  
Code is MIT licensed.
