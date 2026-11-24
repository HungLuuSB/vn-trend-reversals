# VN Bank Data Platform — Project Summary

Nov 24, 2026 · @Hung

## Overview

The VN Bank Data Platform turns Vietnamese bank market data, financial-statement PDFs and news into tested, traceable data for a RAG research assistant, hybrid search, news recommendations and an MCP agent interface. It extends my Big Data course project (Kafka + Spark streaming of bank stock prices) into a production-style AI data platform.

**The demo question:** *"How did VCB's NPL ratio change over the last 4 quarters, and what did the news say about it?"* The agent answers by combining a SQL query on financials with retrieval over filings and news. Every number links back to its source: fact row → extracted table → PDF page → document version → pipeline run.

**Why this project:** it covers every core requirement and most "preferred" items of the AI Data Engineer JD (CDC, Airflow, dbt, data quality, document parsing → chunking → embedding → indexing, search and vector databases, MCP, lineage). It also solves problems that are genuinely hard rather than tool demos: extracting tables from PDFs, point-in-time correctness, and versioning restated reports.

**Target:** a solo build over about 10–12 weeks. Phases 0–4 are the core; phase 5+ is optional polish.

## Scope and data sources

Scope is the roughly 27 listed Vietnamese banks. Banks share one financial-statement format (different from ordinary companies), so the line-item mapping is built once; other sectors can be added later as a schema-evolution exercise.

| Source | Data type | What it provides | How it is ingested |
| --- | --- | --- | --- |
| vnstock (Python library) | Semi-structured JSON | Prices, trades, index data, company info | Kafka producer, streaming + historical backfill |
| Brokerage database (simulated, PostgreSQL) | Structured | Accounts, watchlists, holdings, orders | Debezium CDC → Kafka |
| Financial statements and annual reports | Unstructured PDF (some scanned) | Balance sheet, income statement, notes, narrative | Airflow crawler → MinIO, versioned by content hash |
| News RSS feeds | Semi-structured text | Articles mentioning banks | Incremental Airflow DAG with a watermark per source |

Check each site's terms of use before crawling, and keep the original raw files so any parsing step can be rerun.

## Architecture overview

Data moves from four sources down through five layers; lineage, monitoring and infrastructure span all of them.

&#91;embedded content: platform architecture · 4 sources, 5 layers, cross-cutting ops\]

The highlighted layers are the AI-facing contract: everything above them exists to make their inputs correct, fresh and traceable.

## Technology choices by layer

Each tool has one job; the "why" column is what to say in an interview.

| Layer | Tool | Role | Why this choice | Watch out for |
| --- | --- | --- | --- | --- |
| Ingestion | Kafka | Durable event log between producers and consumers | Decoupling, buffering when a consumer is down, replay from any offset | Partitions, consumer groups, at-least-once vs exactly-once |
| Ingestion | Debezium on Kafka Connect | CDC from the PostgreSQL write-ahead log | Captures deletes and every change, keeps order, no query load (unlike polling `updated_at`) | Replication slots grow if the connector stops |
| Ingestion | Schema Registry + Avro | Enforced contract for event shape | Incompatible changes are rejected at publish time | Pick a compatibility mode (e.g. BACKWARD) deliberately |
| Storage | MinIO | Immutable raw layer: PDFs, raw JSON, HTML | Rerun parsers without re-downloading; same API as AWS S3 | Never edit raw files; write new versions |
| Storage | ClickHouse | Analytics store: prices, CDC tables, marts, features | Columnar: fast scans, 5–10x compression; materialized views; `ASOF JOIN` | `ReplacingMergeTree` dedups only eventually: query with `FINAL` or `argMax` |
| Storage | PostgreSQL | OLTP source + operational metadata (document registry, watermarks, Airflow/Marquez backends) | Good at single-row updates, where ClickHouse is weak | Keep it small; no analytics here |
| Processing | Airflow | Scheduling and dependencies for batch work | Retries, timeouts, backfills, sensors, alerts | Doesn't run streaming; Kafka consumers run on their own |
| Processing | dbt (`dbt-clickhouse`) | SQL models with tests, contracts, docs, incremental loads | Turns SQL scripts into tested, versioned code | SQL in dbt; parsing and entity resolution stay in Python |
| Processing | Great Expectations | Data quality checks, including before loading | Richer rules than dbt tests; checks extracted tables in Python | Failed batches go to quarantine, never downstream |
| AI-ready | Docling, OCR (Tesseract or PaddleOCR), pdfplumber/Camelot | Layout-aware PDF parsing and table extraction | Keeps table rows and columns that plain extractors scramble | Benchmark Vietnamese OCR before choosing |
| AI-ready | BGE-M3 | Embedding model | Multilingual incl. Vietnamese, 8,192-token input, dense + sparse vectors, runs locally | Needs a GPU or patience for batch embedding |
| AI-ready | OpenSearch | BM25 keyword search | Exact matches for tickers, line items, numbers | Use the ICU tokenizer for Vietnamese |
| AI-ready | Qdrant | Vector search (HNSW) with metadata filters | Finds paraphrases that keyword search misses | pgvector or OpenSearch k-NN can replace it if RAM is tight |
| Serving | FastAPI | Data API and Search API | Pydantic validation, auto OpenAPI docs; the API is the contract | Agents and apps never query databases directly |
| Serving | MCP server | Tools and resources for AI agents | The JD's "MCP-compatible Data Service" | Shares one service layer with FastAPI |
| Cross-cutting | OpenLineage + Marquez | Lineage events and lineage graph UI | Standard integrations for Airflow and dbt | Add cell-level lineage via metadata columns yourself |
| Cross-cutting | Prometheus + Grafana | Metrics, dashboards, alerts | Industry-standard monitoring stack | Alert on freshness, not just failures |
| Cross-cutting | Docker Compose, GitHub Actions, Kubernetes | Reproducible env, CI, cloud-native deploy | One-command setup; K8s with Strimzi and the ClickHouse operator | Kubernetes last, after everything works |

**Not used: Spark.** At this data size (dozens of banks, millions of rows), ClickHouse plus dbt does the job with far less to operate. The one sensible place for it is replacing the Python Kafka consumer with Spark Structured Streaming.

## Data model and AI-ready datasets

The dbt project follows staging → intermediate → marts, with point-in-time correctness and versioning built into the core tables.

**Core marts (ClickHouse)**

| Model | Grain | Key columns | Notes |
| --- | --- | --- | --- |
| `fct_prices_daily` | ticker × trading day | open, high, low, close, volume, adj\_close | Adjusted for dividends and splits |
| `fct_financials` | ticker × period × line item × version | value, unit, source\_doc\_id, page, published\_at | Long format; restatements add a new version |
| `fct_news_mentions` | article × ticker | published\_at, match\_method, confidence, dup\_cluster\_id | From entity resolution + MinHash dedup |
| `dim_bank` | ticker | name, aliases, exchange | Alias table feeds entity resolution |
| `dim_line_item` | standard line item | Vietnamese source labels, category | The standard chart of accounts |
| `fct_user_interest` | user × ticker | from watchlists, holdings, orders (CDC) | Input for recommendations |

**Point-in-time rule:** any feature or answer "as of" date D only uses rows with `published_at <= D` (ClickHouse `ASOF JOIN`). This prevents look-ahead leakage in ML features.

**AI-ready datasets**

- **Text chunks:** narrative sections of reports and news, split by headings, then tokens.
- **Table chunks:** each extracted table kept whole, stored as structured rows plus a short text summary for embedding.
- **Chunk metadata:** `chunk_id, doc_id, doc_version, content_hash, ticker, period, report_type, page, section, pipeline_run_id`.
- **Retrieval golden set:** 150–300 questions with the relevant chunk IDs, evaluated with `ranx` (Recall@k, MRR, NDCG).
- **Recommendation dataset:** user × item (news or filing) interactions with timestamps, split by time for offline evaluation.

## Data quality, lineage and monitoring

Quality checks block bad data before it reaches any AI consumer; failed batches go to a quarantine table and trigger an alert.

| Dimension | Check | Tool |
| --- | --- | --- |
| Accuracy | Daily price move within the exchange limit (±7% HOSE, ±10% HNX, ±15% UPCoM) | dbt test / GE |
| Accuracy | Total assets = Liabilities + Equity on every extracted balance sheet | GE (before load) |
| Completeness | Every trading day on the exchange calendar has price data | dbt test |
| Freshness | Prices within N minutes during trading hours; filings indexed within N hours of download | dbt source freshness + Prometheus |
| Duplicates | Unique keys per grain; near-duplicate news clustered by MinHash | dbt test + Python |
| Nulls | Required columns not null in staging and marts | dbt test |
| Schema change | Schema Registry compatibility; dbt contracts; drift check on API responses | Registry + dbt + GE |
| Consistency | CDC row counts in ClickHouse match PostgreSQL | Reconciliation DAG |

**Lineage**

- Pipeline level: OpenLineage events from Airflow and dbt, shown as a graph in Marquez.
- Cell level: every fact row and chunk carries `doc_id`, `doc_version`, `page` and `pipeline_run_id`, so a number in an AI answer traces to the exact PDF page and run.

**Monitoring (Prometheus + Grafana)**

- Kafka consumer lag and CDC latency (PostgreSQL write → ClickHouse).
- DAG success rate and duration; quality checks failed per run.
- Filings waiting to be parsed; PDF extraction failure rate.
- Search and API latency (p95); index freshness.

## Production-readiness drills

These drills separate the project from a tool demo; each gets a short write-up in `docs/` with what was done, what was observed and the result.

| Drill | How | Pass criterion |
| --- | --- | --- |
| Consumer crash | Kill the ClickHouse consumer mid-stream, then restart | Zero duplicates, zero lost events |
| Idempotent backfill | Reprocess one month of prices twice | Identical row counts and checksums |
| Schema evolution | Add a column and change a type in PostgreSQL | Registry, dbt contracts and GE behave as documented |
| Restated report | Load an amended financial statement | Version 2 stored, only changed chunks re-embedded, answers cite version 2 |
| Quality failure | Inject a balance sheet that violates the accounting identity | Batch quarantined, downstream blocked, alert fired |
| Source outage | Make vnstock unavailable for 30 minutes | Retries with backoff; freshness alert; catches up afterwards |

**Stated targets (SLOs):** prices fresh within 5 minutes during trading hours; a new filing searchable within 6 hours; Search API p95 under 500 ms.

**Benchmark table for the README:** events per second ingested, rows processed, PDFs parsed and pass rate, chunks indexed, search latency p95.

## Roadmap

The core build is phases 0–4 over about 10 weeks; each phase ends with a working, demoable system and a pass/fail gate.

&#91;embedded content: roadmap · 6 phases over about 12 weeks\]

Before starting Phase 1, use week 1 to confirm that filing PDFs for 5 banks can be downloaded reliably; Phase 3 depends on it.

## Repo layout

One monorepo, organized by layer so each folder maps to a section of this document.

```
vn-bank-data-platform/
├── docker/            # compose files, per-service configs
├── ingestion/
│   ├── market/        # Kafka producers (vnstock)
│   ├── brokerage_sim/ # Postgres OLTP simulator
│   ├── filings/       # crawler → MinIO
│   └── news/
├── cdc/               # Debezium connector configs
├── airflow/dags/
├── dbt/               # models, tests, contracts
├── quality/           # GE suites / custom checks
├── documents/         # parse, extract tables, chunk, embed, index
├── serving/
│   ├── api/           # FastAPI
│   └── mcp/           # MCP server
├── eval/              # golden set, ranx retrieval eval
├── monitoring/        # Prometheus, Grafana dashboards
├── docs/              # architecture, runbooks, ADRs, drill write-ups
└── tests/
```

## JD coverage matrix

Every core requirement is covered by phases 0–4; the preferred items are mostly covered too.

| JD item | Where in the project | Phase |
| --- | --- | --- |
| SQL and Python | dbt models, ClickHouse queries; producers, parsers, APIs | All |
| ETL/ELT pipelines in production | Airflow + dbt pipelines with drills and SLOs | 1–2 |
| Ingest from DB, API, file, object storage, log | PostgreSQL CDC, vnstock API, PDFs in MinIO, Kafka event log | 1–3 |
| Batch, incremental, CDC, near real-time | Backfill DAGs, watermarked news DAG, Debezium, price stream | 1–2 |
| Apache Airflow | All batch orchestration | 2 |
| dbt | Staging → intermediate → marts, tests, contracts | 2 |
| Clean, standardize, enrich, dedup, validate | Line-item mapping, entity resolution, MinHash, GE | 2–3 |
| Data modeling, relational DBs | Brokerage OLTP schema; ClickHouse marts | 1–2 |
| Retry, idempotency, schema evolution | Drills: consumer crash, double backfill, schema change | 1–2 |
| Document ingestion (PDF, HTML, website) | Filings crawler + Docling/OCR; news HTML | 3 |
| Parsing, chunking, metadata, versioning, embedding, indexing | Document pipeline with content hashes and BGE-M3 | 3–4 |
| Search engine + vector DB pipelines | OpenSearch + Qdrant, hybrid search | 4 |
| Data quality checks and monitoring | Quality table above; Grafana dashboards | 2, 5 |
| Serve data via DB, API, search index | FastAPI Data + Search API | 4 |
| Support agents: Data API, Search API, MCP | MCP server sharing the API service layer | 4 |
| Data lineage to AI application | OpenLineage + Marquez; cell-level lineage | 3, 5 |
| REST API, Git, Docker | FastAPI, monorepo + CI, Docker Compose | 0, 4 |
| Structured, semi-structured, unstructured data | Prices/DB, JSON/RSS, PDFs | 1–3 |
| LLM, RAG, embedding, vector search basics | RAG demo, golden-set retrieval evaluation | 4 |
| Preferred: ClickHouse | Main analytics store | 1 |
| Preferred: Kafka, Debezium, streaming | Price stream + CDC | 1 |
| Preferred: Elasticsearch/OpenSearch | Keyword index | 4 |
| Preferred: Milvus/Qdrant/pgvector | Qdrant | 4 |
| Preferred: Great Expectations | Pre-load and warehouse checks | 2–3 |
| Preferred: OpenLineage | Airflow and dbt integrations | 5 |
| Preferred: Recommendation / Search in production | News and filings recommendations; hybrid search | 4–5 |
| Preferred: Kubernetes, cloud-native | kind/k3d with Helm and operators | 6 |

## Risks, trade-offs and talking points

The biggest risk is filing availability: confirm it in week 1, before committing to Phase 3.

**Risks and mitigations**

| Risk | Mitigation |
| --- | --- |
| Can't reliably download 2–3 years of statements for 5 banks | Test in week 1; fall back to fewer banks or a manually curated PDF set |
| vnstock data sources or API change between versions | Pin the version; wrap it in your own client module |
| Poor Vietnamese OCR on scanned PDFs | Compare Tesseract (vie) and PaddleOCR on 3 pages; report pass rate honestly |
| Full stack exceeds 16 GB RAM | Docker Compose profiles per phase; small JVM heaps; drop Qdrant for pgvector if needed |
| Scope creep | Phases 0–4 are the core; stop there if applying soon |

**Deliberate trade-offs to explain**

- ClickHouse + dbt instead of Spark, because the data volume doesn't justify a cluster.
- Two stores (PostgreSQL + ClickHouse), each used for what it does well.
- Two indexes (OpenSearch + Qdrant) justified by measured hybrid-search gains; otherwise simplify.

**CV bullets to aim for (fill in real numbers)**

- Built a CDC pipeline (Debezium, Kafka) from PostgreSQL to ClickHouse with N s end-to-end latency and zero duplicates after consumer-crash tests.
- Extracted financial tables from N bank reports with X% passing the accounting-identity check; versioned restatements end to end.
- Built hybrid retrieval (OpenSearch + Qdrant, BGE-M3) improving Recall@10 from X to Y on a 200-question golden set.
- Exposed data to AI agents through FastAPI and an MCP server, with lineage from each answer to its source PDF page.

**Deliverables that matter most:** a README with the architecture diagram and benchmark table, drill write-ups in `docs/`, and a 3–5 minute demo video.
