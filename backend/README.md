# Price Agent — backend and local dashboard

The backend uses Python 3.11+, asyncio, `httpx` (optional, policy-gated
retailer HTTP transport), BeautifulSoup for JSON-LD parsing, and SQLite with
WAL, foreign keys, and append-only history. The dashboard uses **FastAPI +
Jinja2** and local CSS/JavaScript. **Network retailer ingestion is disabled
by default.** The root `price_agent.py` is still a separate mock-data ReAct
experiment; the UI does not claim to have connected that mock agent to live
retailers.

## Install and test

From the root of your VS Code `Price-agent` checkout, in PowerShell:

```powershell
python -m pip install -r backend/requirements-dashboard.txt
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m unittest discover -s tests -v
python -m pytest -q tests
```

For type-checking and property-test development, install the optional developer
requirements and run `python -m mypy --strict price_engine`. The original audit
container did not have mypy or Hypothesis installed, and installation was
blocked by unavailable DNS: **strict mypy and Hypothesis remain unverified**.
Do not treat the pytest/unittest pass as a substitute for strict typing.

## Launch the read-only Phase 4 dashboard

Still inside `backend/`:

```powershell
# Only if you have NOT already initialized this demo filename:
python -m price_engine.demo --db demo_fresh.sqlite3
python -m price_engine.dashboard --db demo_fresh.sqlite3 --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000> for price history and
<http://127.0.0.1:8000/catalog> for the Phase 5 catalog. The demo uses
an **offline synthetic HTML fixture**, not a live retailer quote. Run
the demo command **only once per new database filename**. Re-running it
against an existing database can raise
`ValueError: Conflicting duplicate observation ID or source record`:
the fixture reuses a source record ID but supplies a new observation
timestamp. This is deliberate append-only storage protection. Preserve
your database; skip the demo step on subsequent runs, or select a new
database filename. The catalog page displays no imported products until
you explicitly run the Open Food Facts importer.

### Endpoints

| Method and endpoint | Behavior |
|---|---|
| `GET /` | Responsive HTML dashboard with auto-refresh every 30 seconds |
| `GET /api/listings?limit=50&offset=0` | Active listings with latest verified status, integer paisa, formatted price, stale indicator, and up to 60 accepted 30-day trend samples |
| `GET /api/listings/{listing_id}/history?days=30` | Accepted, in-stock observations in UTC, exact paisa fields, count, total, rounded display average, low, and at most 10,000 chart points |
| `GET /api/health` | Read-only DB and configured-scheduler status (`NOT_CONFIGURED` by default) |
| `GET /catalog` | Phase 5 product catalog UI with Open Food Facts attribution |
| `GET /api/catalog/stats` | Actual imported product count and last import timestamp |
| `GET /api/catalog/search?q=oats&limit=25&offset=0` | FTS5 indexed lookup by name/brand/category; at most 100 results per page |

The dashboard uses separate `file:...?...mode=ro` SQLite connections,
`PRAGMA query_only=ON`, short read transactions, parameterized SQL and
FastAPI's threadpool for synchronous SQLite operations. It **never runs
schema migrations** and has **no write/trigger API**. Quarantined or
out-of-stock latest observations cannot become a displayed current price.
Previously accepted prices older than 24 hours are marked **STALE** rather
than presented as live quotes.

**Security:** Default bind is `127.0.0.1`. Do not expose this unauthenticated
read-only dashboard publicly; add authentication, TLS, network isolation and
production operational monitoring first. Static assets are served locally
without external CDN code. Browser requests must not scrape retailers.

## Ingestion API and hardening

- `HybridRouter.ingest(...)` returns a verified/typed observation;
  `ingest_tool(...)` returns `{ok, error, retryable, status, price_paisa,
  price_display, ...}` with exhaustive status handling.
- `StructuredHTMLClient` is disabled by default and requires documented
  authorization plus an **injected shared `httpx.AsyncClient`**. Construct it
  with explicit `httpx.Limits` and an explicit `httpx.Timeout` that sets
  connect, read, write and pool, `trust_env=False`, and
  `follow_redirects=False`. The caller owns and closes the shared client.
- 429 and 503 with Retry-After impose per-host cooldown, 403 denies without
  retry or HTML fallback; three repeated DOM errors quarantine that adapter
  and host. No CAPTCHA bypass, proxy rotation, or browser evasion exists.
- `TokenBucket` accepts an injected monotonic clock; global and per-host
  request semaphores are acquired in that order, only during the request.
- `AsyncPriceStore` moves SQLite calls to a bounded single-slot worker bridge;
  cancellation does not release the slot before a thread completes.
- `PriceStore.price_window(...)` computes an exact 30-day accepted-price
  sum/count/low; `PriceWindow.qualifies(...)` applies integer-paisa 10%-below,
  5%-above-low, budget, stock and Decimal rating checks (minimum 10 samples).
- The `PollingScheduler` is **opt-in**, injected-callback only, bounded,
  jittered, and prevents overlapping listing polls. The demo/dashboard does
  **not** start it or contact retailers. `close()` drains the queue with a
  configurable timeout and cancels idle worker tasks.
- Writes remain parameterized, atomic, and append-only. A duplicate poll
  ID with changed payload raises a conflict instead of silently overwriting.
  Distinct polling cycles get distinct record IDs. The existing SQL schema
  and history update/delete triggers were not changed.

### Run the socket-pool benchmark (loopback only)

```powershell
python -m benchmarks.loopback
```

This binds a synthetic 25 ms latency server **only on `127.0.0.1`** and
uses 120 asynchronous tasks with 20 concurrent HTTP connections, so it
exercises connection pooling (unlike `MockTransport`). Fault scenarios with
cooldown are not directly comparable to the original baseline: deferred
requests intentionally avoid HTTP traffic.

## Remaining blockers before external production deployment

Authorized retailer API adapters and contract tests, **DNS resolution pinned
across connect** (the current public-address preflight is not DNS-rebinding
proof), cross-process persistent rate limits/circuit state, ingestion-attempt
logging/observability, database migration versioning, ReAct tool integration
with SQLite rather than its USD mock data, authentication if externally
exposed, verified strict mypy and Hypothesis checks, and real-world load
measurements are still required. Do **not** switch on retailer extraction
based solely on fixture tests.

## Phase 5 — imported open-data catalog

Phase 5 is **merged into `main`** through [PR #3](https://github.com/iam-Seraph/Price-agent/pull/3) (merge `a7cd7e1f12dd7a6e688bc8ea54f01d985fdcf142`).
This is a separate **Open Food Facts** product-identity catalog, not a
price-source adapter. New components:

- `migrations/002_catalog.sql`: independent `product_catalog` and
  `catalog_import_runs` tables, FTS5 index with insert/update/delete
  triggers. The Phase 1 `001_initial.sql` and append-only price-history
  triggers are unchanged.
- `price_engine/catalog_import.py`: streaming compressed/uncompressed
  official CSV/TSV export, numeric barcode validation, restricted-category
  exclusions, 2,000-row default upsert batches and actual-count reporting.
- `price_engine/catalog_api.py`: read-only FTS5 search and stats routes.
  The UI shows source links, never inferred prices.
- `price_engine/templates/catalog.html` and `static/catalog.js`:
  paginated browser UI. Search uses query parameters (max 100 chars),
  at most 100 results/page, and offsets up to 1,000,000.

The import cap is **accepted source rows, not unique products**. Invalid
or duplicate records can reduce the unique count below the target.
No million-row import or load benchmark is established by unit tests.

### Import on Windows (PowerShell)

Use the **same SQLite database filename** for the importer and dashboard.
If you already have `backend/demo_fresh.sqlite3`, skip the demo setup.

~~~powershell
# From repository root:
python -m pip install -r backend/requirements-dashboard.txt
New-Item -ItemType Directory -Force backend/data | Out-Null
curl.exe -L --fail --retry 3 "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz" -o "backend/data/openfoodfacts.csv.gz"
cd backend
# Optional first sample run:
python -m price_engine.catalog_import --input data/openfoodfacts.csv.gz --db demo_fresh.sqlite3 --max-rows 10000
# Target up to one million accepted input rows:
python -m price_engine.catalog_import --input data/openfoodfacts.csv.gz --db demo_fresh.sqlite3 --max-rows 1000000
python -m price_engine.dashboard --db demo_fresh.sqlite3 --host 127.0.0.1 --port 8000
~~~

Open `http://127.0.0.1:8000/catalog`, then `/api/catalog/stats`
for the *actual* unique product count. Large exports can consume many GB
of network and disk. Upstream export downloads are user-initiated, not
shipped in the Git repository or executed by CI. When the named SQLite
database does **not exist**, create the legacy price schema with the
demo command **once** before opening the overview dashboard.

Open Food Facts data is community-maintained and licensed under **ODbL**.
Give contributors attribution and follow database share-alike obligations.
Product names, codes, categories and source links do **not** establish
retailer prices, stock or a trustworthy seller rating. See [PHASE5.md](../PHASE5.md).

## Verification and release history

- **PR #1** ([hardening/dashboard](https://github.com/iam-Seraph/Price-agent/pull/1)):
  18 November 2026, merge `89f6b0fa343502797ba697252afb021497ac0b66`.
  Original offline release evidence: 34 backend unittest tests.
- **PR #2** ([docs/audit sync](https://github.com/iam-Seraph/Price-agent/pull/2)):
  18 November 2026, merge `5deaee07080b3e2f201a112f7a73f832d154af87`.
- **PR #3** ([Phase 5](https://github.com/iam-Seraph/Price-agent/pull/3)):
  18 November 2026, merge `a7cd7e1f12dd7a6e688bc8ea54f01d985fdcf142`.
  [GitHub Actions](https://github.com/iam-Seraph/Price-agent/actions/runs/44166599779):
  **37 backend unittest tests passed** with Python 3.11, and Python
  compilation passed. These tests used small local fixtures, not real
  bulk downloads.

Strict mypy and Hypothesis are still not independently verified, nor is
a million-row import, live-retailer authorization or production load.
The dashboard is **local and unauthenticated**. The root ReAct agent still
uses separate USD mock data, not imported catalog records.

Read the [root README](../README.md) for a unified quick start,
[PHASE5.md](../PHASE5.md) for the complete import/license guide and
[AUDIT.md](../AUDIT.md) for preserved historical audit findings.
