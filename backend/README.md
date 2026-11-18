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
python -m price_engine.demo --db price_engine.sqlite3
python -m price_engine.dashboard --db price_engine.sqlite3 --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. The demo uses an **offline synthetic HTML
fixture**, not a real retailer quote. The second run of the demo against the
same database reports `inserted: False` because the fixture uses a stable
record ID.

### Endpoints

| Method and endpoint | Behavior |
|---|---|
| `GET /` | Responsive HTML dashboard with auto-refresh every 30 seconds |
| `GET /api/listings?limit=50&offset=0` | Active listings with latest verified status, integer paisa, formatted price, stale indicator, and up to 60 accepted 30-day trend samples |
| `GET /api/listings/{listing_id}/history?days=30` | Accepted, in-stock observations in UTC, exact paisa fields, count, total, rounded display average, low, and at most 10,000 chart points |
| `GET /api/health` | Read-only DB and configured-scheduler status (`NOT_CONFIGURED` by default) |

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

## Release and documentation status

The Phase 2 hardening and Phase 4 dashboard code was merged to GitHub `main`
via [PR #1](https://github.com/iam-Seraph/Price-agent/pull/1) on 2026-11-18
(merge commit `89f6b0fa343502797ba697252afb021497ac0b66`).
See the [root README](../README.md) for the consolidated project quick start,
and [AUDIT.md](../AUDIT.md) for preserved findings, historical test evidence,
actual published commit hashes, and outstanding limitations. Those historical
offline test results are not fresh GitHub CI results.

## Phase 5 — real product catalog

The separate Open Food Facts importer and FTS5 search page live on the Phase 5
feature branch. They add real product identities only; they do NOT add live
retailer prices, stock or AI-agent linkage. The official bulk export is large,
downloaded by the user, and kept out of Git.

From the repo root (PowerShell):

~~~powershell
python -m pip install -r backend/requirements-dashboard.txt
New-Item -ItemType Directory -Force backend/data | Out-Null
curl.exe -L --fail --retry 3 "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz" -o "backend/data/openfoodfacts.csv.gz"
cd backend
python -m price_engine.catalog_import --input data/openfoodfacts.csv.gz --db demo_fresh.sqlite3 --max-rows 1000000
python -m price_engine.dashboard --db demo_fresh.sqlite3 --host 127.0.0.1 --port 8000
~~~

Open http://127.0.0.1:8000/catalog for indexed product search.
Use the SAME database for the import and dashboard. The importer creates the
catalog schema; the existing demo database supplies the older price schema.

New read-only routes: GET /catalog, GET /api/catalog/stats, and
GET /api/catalog/search (q, limit<=100, offset). The catalog is independent
of products, retailer_listings, and append-only price_history tables.
Tests: python -m unittest discover -s tests -v from backend.

For data provenance, ODbL obligations, import limits, troubleshooting and
clear distinctions between a 1M-row target and actually imported records,
see [PHASE5.md](../PHASE5.md).
