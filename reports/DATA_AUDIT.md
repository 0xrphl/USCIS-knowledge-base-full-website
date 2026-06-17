# 📊 USCIS Knowledge Base — Data Audit Report

> **Generated from:** `db_cluster-26-07-2025@08-08-01.backup`  
> **Backup date:** July 26, 2025  
> **Database:** PostgreSQL 15 (Supabase)  
> **Total DB size:** ~3 GB (449 MB content + 795 MB embeddings)

---

## 1. High-Level Summary

| Metric | Value |
|---|---|
| Total content chunks | **99,489** |
| Unique URLs scraped | **4,666** |
| Processed URLs tracked | **4,666** (100% match) |
| Total embeddings | **99,488** (99.999% coverage) |
| Content without embedding | **1** chunk |
| URLs with missing chunks | **1** URL (7 missing chunks) |
| Total DB size | **~1.24 GB** (content + embeddings) |

---

## 2. Table Row Counts

| Table | Rows | Size |
|---|---|---|
| `uscis_content` | 99,489 | 449 MB |
| `uscis_embeddings` | 99,488 | 795 MB |
| `processed_urls` | 4,666 | 664 KB |
| `scraping_metadata` | 28 | 16 KB |
| `assessments` | 5 | 48 KB |
| `form_submissions` | 0 | 8 KB |

---

## 3. Content Analysis

### 3.1 Document Types

| Document Type | Chunks | % of Total |
|---|---|---|
| PDF | 55,957 | 56.2% |
| Web Page | 32,625 | 32.8% |
| Policy Manual | 8,886 | 8.9% |
| Form | 1,156 | 1.2% |
| News | 800 | 0.8% |
| Image | 65 | 0.1% |

### 3.2 Immigration Categories

| Category | Chunks | % of Total |
|---|---|---|
| General | 92,520 | 93.0% |
| Humanitarian | 2,488 | 2.5% |
| Employment | 2,219 | 2.2% |
| Permanent Residence | 1,553 | 1.6% |
| Citizenship | 573 | 0.6% |
| Family | 136 | 0.1% |

### 3.3 Content Length Statistics

| Metric | Characters |
|---|---|
| Minimum | 3 |
| Average | 1,426 |
| Median | 1,372 |
| Maximum | 7,999 |

### 3.4 Chunking Statistics

| Metric | Value |
|---|---|
| Multi-chunk URLs | 1,685 (36.1%) |
| Single-chunk URLs | 3,077 (65.9%) |
| Min chunk_num | 1 |
| Max chunk_num | 5,075 |
| Min total_chunks | 1 |
| Max total_chunks | 5,075 |

---

## 4. Null Value Analysis

### 4.1 `uscis_content` Table

| Column | Null Count | % Null | Notes |
|---|---|---|---|
| `id` | 0 | 0% | Primary key |
| `url` | 0 | 0% | Required field |
| `title` | 0 | 0% | ✅ Fully populated |
| `content` | 0 | 0% | Required field |
| `html` | 90,606 | 91.1% | ⚠️ Expected — PDFs and processed content don't retain HTML |
| `immigration_category` | 0 | 0% | ✅ Fully populated |
| `document_type` | 0 | 0% | ✅ Fully populated |
| `section` | 0 | 0% | ✅ Fully populated |
| `source` | 0 | 0% | ✅ Fully populated |

### 4.2 `uscis_embeddings` Table

| Column | Null Count | % Null |
|---|---|---|
| `id` | 0 | 0% |
| `content_id` | 0 | 0% |
| `embedding` | 0 | 0% |

---

## 5. URL Coverage

| Metric | Count |
|---|---|
| URLs in `processed_urls` | 4,666 |
| Unique URLs in `uscis_content` | 4,666 |
| Processed URLs without content | 0 |
| **Coverage** | **100%** |

---

## 6. Embedding Coverage

| Metric | Count |
|---|---|
| Total content chunks | 99,489 |
| Total embeddings | 99,488 |
| Unique content IDs with embeddings | 99,488 |
| **Content without embedding** | **1** |
| Null embeddings | 0 |
| **Coverage** | **99.999%** |

---

## 7. Scraping Metadata

| Status | Sessions | Pages Scraped | With Errors |
|---|---|---|---|
| running | 28 | 0 | 0 |

> **Note:** All 28 scraping sessions show `status=running` with `pages_scraped=0`. This suggests the page counter wasn't updated during scraping (the actual scraping completed successfully as evidenced by 4,666 URLs with content).

---

## 8. Data Quality Score

| Check | Status | Score |
|---|---|---|
| All URLs have content | ✅ Pass | 100% |
| All content has embeddings | ⚠️ 1 missing | 99.999% |
| No null required fields | ✅ Pass | 100% |
| Chunk sequence integrity | ⚠️ 1 URL with gaps | 99.98% |
| Embedding vectors complete | ✅ Pass | 100% |
| **Overall Data Quality** | **✅ Excellent** | **99.99%** |
