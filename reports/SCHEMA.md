# 🗄️ Database Schema Documentation

> **Database:** PostgreSQL 15 with pgvector extension  
> **Source:** Supabase (self-hosted restore)

---

## Entity Relationship Diagram (Text)

```
┌─────────────────────┐       ┌─────────────────────┐
│   processed_urls    │       │  scraping_metadata   │
├─────────────────────┤       ├─────────────────────┤
│ url (PK)            │       │ id (PK, uuid)       │
│ processed_at        │       │ start_time          │
└────────┬────────────┘       │ end_time            │
         │ url = url          │ pages_scraped       │
         ▼                    │ status              │
┌─────────────────────┐       │ error               │
│    uscis_content     │       │ created_at          │
├─────────────────────┤       └─────────────────────┘
│ id (PK, uuid)       │
│ url (NOT NULL)       │       ┌─────────────────────┐
│ title                │       │    assessments       │
│ content (NOT NULL)   │       ├─────────────────────┤
│ html                 │       │ id (PK, uuid)       │
│ created_at           │       │ created_at          │
│ last_updated         │       │ data (JSONB)        │
│ immigration_category │       └─────────────────────┘
│ document_type        │
│ section              │       ┌─────────────────────┐
│ source               │       │  form_submissions   │
│ chunk_num            │       ├─────────────────────┤
│ total_chunks         │       │ id (PK, uuid)       │
└────────┬────────────┘       │ created_at          │
         │ id = content_id    │ updated_at          │
         ▼                    │ user_id             │
┌─────────────────────┐       │ form_type           │
│  uscis_embeddings   │       │ status              │
├─────────────────────┤       │ data (JSONB)        │
│ id (PK, uuid)       │       └─────────────────────┘
│ content_id (FK)     │
│ embedding (vec 1536)│
│ created_at          │
└─────────────────────┘
```

---

## Table Details

### `uscis_content` — Main content store

The core table holding all scraped and chunked USCIS content.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | Primary key |
| `url` | text | NOT NULL | — | Source URL |
| `title` | text | YES | — | Page title |
| `content` | text | NOT NULL | — | Extracted text content (chunk) |
| `html` | text | YES | — | Raw HTML (null for PDFs) |
| `created_at` | timestamptz | YES | `CURRENT_TIMESTAMP` | When scraped |
| `last_updated` | timestamptz | YES | `CURRENT_TIMESTAMP` | Last update time |
| `immigration_category` | text | YES | — | Category classification |
| `document_type` | text | YES | — | Type: PDF, Web Page, etc. |
| `section` | text | YES | — | USCIS section |
| `source` | text | YES | — | Source identifier |
| `chunk_num` | integer | YES | 1 | Chunk position (1-indexed) |
| `total_chunks` | integer | YES | 1 | Total chunks for this URL |

**Indexes:** `uscis_content_pkey` (btree on `id`)

---

### `uscis_embeddings` — Vector embeddings

Stores OpenAI `text-embedding-ada-002` (1536-dimensional) vectors linked to content chunks.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | Primary key |
| `content_id` | uuid | YES | — | FK → `uscis_content.id` |
| `embedding` | vector(1536) | YES | — | OpenAI embedding vector |
| `created_at` | timestamptz | YES | `CURRENT_TIMESTAMP` | When generated |

**Indexes:** `uscis_embeddings_pkey` (btree on `id`)  
**Foreign Keys:** `content_id` → `uscis_content(id)`

---

### `processed_urls` — URL tracking

Tracks which URLs have been scraped to avoid duplicate processing.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `url` | text | NOT NULL | — | Primary key, the URL |
| `processed_at` | timestamptz | NOT NULL | — | When processed |

**Indexes:** `processed_urls_pkey` (btree on `url`), `idx_processed_urls_url` (btree on `url`)

---

### `scraping_metadata` — Scraping session logs

Tracks scraping session metadata.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | Primary key |
| `start_time` | timestamptz | YES | — | Session start |
| `end_time` | timestamptz | YES | — | Session end |
| `pages_scraped` | integer | YES | 0 | Pages count |
| `status` | text | YES | — | running/completed/failed |
| `error` | text | YES | — | Error message if any |
| `created_at` | timestamptz | YES | `CURRENT_TIMESTAMP` | Record creation |

---

### `assessments` — User assessments

Stores immigration assessment data as JSONB.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | — | Primary key |
| `created_at` | timestamptz | NOT NULL | `now()` | Creation time |
| `data` | jsonb | NOT NULL | — | Assessment data |

**Indexes:** `assessments_pkey` (btree on `id`), `idx_assessments_data` (GIN on `data`)

---

### `form_submissions` — Form data

Stores user form submissions with RLS policies.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | — | Primary key |
| `created_at` | timestamptz | NOT NULL | `now()` | Creation time |
| `updated_at` | timestamptz | NOT NULL | `now()` | Last update |
| `user_id` | text | YES | — | Supabase auth user ID |
| `form_type` | text | NOT NULL | — | Form type identifier |
| `status` | text | NOT NULL | `'draft'` | draft/submitted/etc. |
| `data` | jsonb | NOT NULL | — | Form data |

**Indexes:** Multiple indexes on `id`, `data` (GIN), `form_type`, `status`, `user_id`  
**RLS Policies:** Users can only CRUD their own submissions

---

## Supabase Schemas

| Schema | Description |
|---|---|
| `public` | Application data (tables above) |
| `auth` | Supabase Auth (users, sessions, tokens) |
| `storage` | Supabase Storage (buckets, objects) |
| `realtime` | Supabase Realtime subscriptions |
| `vault` | Supabase Vault (secrets) |
| `extensions` | PostgreSQL extensions |
| `graphql` | GraphQL schema cache |
| `graphql_public` | Public GraphQL interface |
| `pgbouncer` | Connection pooling |
| `supabase_migrations` | Migration tracking |
