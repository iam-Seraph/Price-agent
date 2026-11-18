# Price-Checker & Deal Tracker Agent

Python learning project with three **separate** workflows: mock-data ReAct AI, a standalone live URL price checker, and a hardened SQLite backend with a local read-only dashboard.

> **Status (18 November 2026):** Phases 2–5 are merged into `main`. Phase 5 can import up to **1,000,000 accepted Open Food Facts source rows**, but no million-product dataset is bundled or verified imported. **No automatic retailer tracking or AI-to-catalog integration.** Not production-ready. See [PHASE5.md](PHASE5.md) and [AUDIT.md](AUDIT.md).

## Components

| Component | Command or location | Source of prices | Limits |
| --- | --- | --- | --- |
| ReAct agent | `price_agent.py` | Fictional USD catalog and temporary JSON history | Groq/OpenAI optional; **not connected** to SQLite |
| Standalone URL checker | `live_price.py` | Structured metadata from a permitted HTTPS product URL | Can report price unavailable; **no history** |
| Backend engine | `backend/price_engine/` | Offline fixtures; opt-in approved adapters | Retailer network ingestion disabled by default |
| Phase 4 dashboard | `backend/price_engine/dashboard.py` | Existing local SQLite history | Read-only; no manual fetch or running scheduler by default |
| Phase 5 catalog | `backend/price_engine/catalog_import.py` | Real Open Food Facts names, barcodes and metadata | Manual bulk import; read-only `/catalog` search; **no retailer prices** |

The backend uses **integer INR paisa** for prices. The legacy root agent uses **fictional USD**, so their values and verdicts must not be mixed. Open Food Facts catalog records contain **product identity only**, not validated offers or price history.

## Requirements and setup

Use **Python 3.11+** for the whole repository. In VS Code, open this repository and choose **Terminal → New Terminal**. In PowerShell from the repository root:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements-dashboard.txt
```

For macOS/Linux activate with `source .venv/bin/activate` instead. The dashboard dependencies include the root application requirements. Install `backend/requirements-dev.txt` separately to run pytest, mypy and property-test tooling.

## Start the local dashboard (Phases 4 and 5)

After installing dependencies, from the repository root:

~~~powershell
cd backend
# Run only once, when creating a NEW demo database:
python -m price_engine.demo --db demo_fresh.sqlite3
python -m price_engine.dashboard --db demo_fresh.sqlite3 --host 127.0.0.1 --port 8000
~~~

Open **http://127.0.0.1:8000** for sample price history and **http://127.0.0.1:8000/catalog** for product catalog search. Keep the terminal open; press **Ctrl+C** to stop the server. If `demo_fresh.sqlite3` already exists and contains the demo record, **skip the demo command**.

**Known demo rerun error:** The demo uses a stable source record ID with a new timestamp. Re-running it against an existing populated database can raise `ValueError: Conflicting duplicate observation ID or source record`. The database conflict is intentional in append-only storage. Preserve the existing file and skip the demo, or choose a NEW database filename. Do not delete a database containing records you need. The demo uses synthetic local HTML, **not a genuine retailer quote**.

- The dashboard uses SQLite read-only connections and cannot migrate, register products, trigger retailer requests or start a scheduler.
- Price-history statuses: `VALID_PRICE`, `OUT_OF_STOCK`, `QUARANTINED` and `UNAVAILABLE`; observations over 24 hours old are marked stale. Browser data refreshes every 30 seconds.
- The Phase 5 catalog remains empty until a local export is imported. It is separate from retailer prices and the Groq AI agent.
- The server has no authentication; **only bind it to `127.0.0.1`**.

### Read-only routes

| Route | Description |
| --- | --- |
| `GET /` | Price-history overview |
| `GET /api/listings?limit=50&offset=0` | Active listings and latest observed status |
| `GET /api/listings/{listing_id}/history?days=30` | Accepted in-stock price history |
| `GET /api/health` | Database and scheduler status |
| `GET /catalog` | Searchable real-product catalog page |
| `GET /api/catalog/stats` | True count of unique imported products and last completed import |
| `GET /api/catalog/search?q=oats&limit=25&offset=0` | Indexed product/brand/category search, up to 100 rows/page |

See [backend/README.md](backend/README.md) for the implementation and [PHASE5.md](PHASE5.md) for catalog import details.

## Import real-product data (Phase 5)

**Import is optional and can require significant disk space and bandwidth.** Download the official Open Food Facts bulk export. From the repository root:

~~~powershell
New-Item -ItemType Directory -Force backend/data | Out-Null
curl.exe -L --fail --retry 3 "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz" -o "backend/data/openfoodfacts.csv.gz"
cd backend
# Test a small import first:
python -m price_engine.catalog_import --input data/openfoodfacts.csv.gz --db demo_fresh.sqlite3 --max-rows 10000
# Attempt up to one million accepted input rows:
python -m price_engine.catalog_import --input data/openfoodfacts.csv.gz --db demo_fresh.sqlite3 --max-rows 1000000
~~~

Use the **same SQLite filename** for the import and the dashboard. The importer accepts real product identities and metadata from Open Food Facts, **not price quotes**. `--max-rows` limits accepted input rows, not guaranteed distinct stored products. Duplicates, invalid records, and category exclusions can reduce the final count. View `/api/catalog/stats` to verify the actual count. The export is not bundled or fetched by CI; no million-product import or benchmark has been confirmed.

The source is attributed to **Open Food Facts contributors** and subject to **ODbL** obligations. See [PHASE5.md](PHASE5.md) for source/license information, accepted formats, filtering, and troubleshooting.

## Run the root mock-data ReAct agent

Run six offline mock test cases (A, B, C1, C2, D, E) without an API key:

```powershell
# From the repository root
python price_agent.py
```

For an LLM call, copy `.env.example` to an untracked local `.env`, set `AI_PROVIDER=groq` and your own `GROQ_API_KEY`. The implementation defaults to `GROQ_MODEL=llama-3.3-70b-versatile`; verify that model is still available from your provider before use.

```powershell
python price_agent.py --product headphones-a --budget 280
```

Alternatively, configure `AI_PROVIDER=openai`, `OPENAI_API_KEY`, and **a verified model ID** in `OPENAI_MODEL`. The old `gpt-6-luna` example in the code/configuration is not a verified model ID; do not rely on it. Model calls can incur charges. The agent has `MAX_STEPS = 6`. Its mock USD results do **not** verify live bargains.

## Standalone product URL checker

From the root:

```powershell
python live_price.py --url "https://www.amazon.in/dp/REAL_ASIN" --budget 3000 --currency INR
```

Replace `REAL_ASIN` with an actual product identifier. Input domains include Amazon India/US, Flipkart, Croma, Reliance Digital, Myntra, Best Buy and Walmart. They are **permitted URL inputs, not guaranteed data integrations**. Retailers may omit metadata or block automation. Missing price is **unavailable**, not zero, out-of-stock, or a confirmed deal. Respect access restrictions; no CAPTCHA/anti-bot circumvention. This command performs live HTTP requests; the offline demo does not.

## Deal rules and history

A backend `PriceWindow` qualifies a deal only when it is within budget, at least **10% below the exact 30-day average**, within **5% above the 30-day low**, **in stock**, and has a trusted seller rating **≥4.0**. It requires at least **10 accepted samples**. Threshold comparisons use integer-paisa sum/count rather than rounded averages. The dashboard is an observation viewer, **not** a live deal-certification system.

The bounded, jittered `PollingScheduler` is opt-in. A live retailer ingestion pipeline and the ReAct-to-SQLite tools are not connected by default.

## Verify locally

~~~powershell
# From the repository root:
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m unittest discover -s tests -v
python -m pytest -q tests
python -m compileall -q price_engine tests
python -m mypy --strict price_engine
python -m benchmarks.loopback
~~~

**Verified CI for Phase 5 PR #3:** 37 backend `unittest` tests passed on Python 3.11, plus Python compilation ([workflow run](https://github.com/iam-Seraph/Price-agent/actions/runs/44166599779)). Tests exercise small offline fixtures, **not** a million-row bulk import, real retailer pricing or production-scale query latency. Earlier Phase 2–4 release evidence recorded **34 offline backend tests**. Strict mypy and Hypothesis remain **unverified**, and localhost benchmarks are not production performance guarantees.

## Repository map

~~~text
Price-agent/
├── README.md                         # Current status and quick start
├── PHASE5.md                         # Real-data import, license and caveats
├── AUDIT.md                          # Original audit and release evidence
├── .github/workflows/phase5.yml      # Backend CI on pull requests
├── .env.example                      # Example credentials only
├── price_agent.py                    # Separate mock USD ReAct agent
├── live_price.py                     # Separate best-effort URL extractor
└── backend/
    ├── README.md                     # Backend and API runbook
    ├── migrations/001_initial.sql    # Append-only price history
    ├── migrations/002_catalog.sql    # Catalog + FTS5 indexes
    ├── price_engine/catalog_import.py
    ├── price_engine/catalog_api.py
    ├── price_engine/dashboard.py
    ├── price_engine/templates/       # Overview + catalog pages
    ├── price_engine/static/          # Local JavaScript/CSS
    ├── requirements-dashboard.txt
    ├── requirements-dev.txt
    ├── benchmarks/loopback.py
    └── tests/test_catalog.py         # Phase 5 fixture-based tests
~~~

## Security and remaining work

- Keep API keys in local `.env` or a secrets manager, never in Git or logs. Rotate any key exposed previously. `.gitignore` does not erase committed secrets.
- Keep the unauthenticated dashboard on `127.0.0.1`. Do not expose it without authentication, TLS and operational controls.
- A real product barcode/name is **not** a verified retailer price or stock observation. Phase 5 does not connect the root ReAct mock agent, backend retailer listings or automatic polling.
- Unfinished engineering work includes authorized retailer API adapters, DNS-pinned SSRF-safe networking, cross-process rate/circuit control, ingestion-attempt logging, durable migration versioning, strict mypy/Hypothesis verification, and genuine 1M-row import/search performance measurements.
- Open Food Facts attribution and ODbL/database redistribution obligations apply to derivative databases. Importer category exclusions are best-effort and must not be treated as exhaustive.

**Documentation:** [PHASE5.md](PHASE5.md) explains the bulk import and license, [backend/README.md](backend/README.md) documents the backend/API, and [AUDIT.md](AUDIT.md) preserves historical findings and merges.

## Release history

| Date | Release | Verified GitHub merge |
| --- | --- | --- |
| 2026-11-18 | Backend hardening and Phase 4 dashboard | [PR #1](https://github.com/iam-Seraph/Price-agent/pull/1), `89f6b0fa343502797ba697252afb021497ac0b66` |
| 2026-11-18 | Documentation and audit synchronization | [PR #2](https://github.com/iam-Seraph/Price-agent/pull/2), `5deaee07080b3e2f201a112f7a73f832d154af87` |
| 2026-11-18 | Phase 5 real catalog importer, FTS5 search, UI, tests and CI | [PR #3](https://github.com/iam-Seraph/Price-agent/pull/3), `a7cd7e1f12dd7a6e688bc8ea54f01d985fdcf142` |

All three are merged into `main`. The Phase 5 release provides **import capability**, not a preloaded million-item dataset or real retailer-price feed.
