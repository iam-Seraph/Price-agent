# Phase 6 checkpoint — Loops 51–60

Source branch: `feat/phase6-unified-workspace`. Builds on the merged Phase 5 alert pipeline. No historical observations are deleted.

--- LOOP [51]: Make real-price workflows available in the local workspace ---
Added verified-price workflow integration while preserving the standalone legacy Intelligence Studio.

--- LOOP [52]: Cross-origin browser protections ---
Extended same-origin POST checks to all verified API mutations. Verified writes require an Origin header and reject cross-site browser requests.

--- LOOP [53]: Explicit real-product search ---
Connected local UI searches to the SerpApi-only provider adapter and SQLite insertion. Rate limit: one search per 15 seconds per server instance. A provider failure never creates fictional prices.

--- LOOP [54]: Local watch management ---
Added opt-in watchlist POST create and disable endpoints. A saved watch does not start a background worker.

--- LOOP [55]: Legacy route non-regression ---
Kept `/intelligence` as the explicitly labeled fictional simulation so old user links and tests still work. Real source-backed offers remain under `/verified`. `/simulation` is an alias to the old route.

--- LOOP [56]: Accurate watch capacity ---
Count only active watches against the 100-watch local limit, rather than permanently counting disabled rules.

--- LOOP [57]: Honest API contracts ---
Documented that the verified API provides both source-attributed reads and explicit, origin-protected writes.

--- LOOP [58]: Integrated browser controls ---
Added real-offer search, saved-watch creation and opt-in alert controls to the existing `/verified` page, with clear data provenance and worker requirements.

--- LOOP [59]: Secure UI workflow ---
Used local JS with textContent-based DOM rendering, same-origin fetch, explicit confirmations, and safe error handling. No API keys are sent from the browser to the server.

--- LOOP [60]: Regression tests ---
Added integration coverage for source-backed ingestion, search throttling, origin checks, persisted watch creation, explicit alert consent, and preserved simulation behavior.

## Start the local application

From the repository root, install dependencies:

```bash
python -m pip install -r backend/requirements-workspace.txt -r backend/requirements-dev.txt
```

Configure a **private** `SERPAPI_KEY` in Codespaces secrets or an ignored local `.env` file. To start the local UI with database `tracker.sqlite3`, first initialize the existing legacy dashboard schema:

```bash
python -c "from backend.price_engine.storage import PriceStore; PriceStore('tracker.sqlite3','backend/migrations/001_initial.sql').close()"
cd backend
python -m price_engine.workspace --db ../tracker.sqlite3 --workspace-db workspace.sqlite3 --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/verified`. The application starts without fetching live prices. Search explicitly through the UI. Saved watches require separately started `price_watch.py` to poll. Email/Telegram delivery requires separately started `price_alert.py` and private credentials.

## Scope limitations
- No live Groq or SerpApi call has been verified without operator credentials.
- This is a **single-operator, loopback-only development** app; do not expose it publicly.
- A browser click alone never purchases products or begins indefinite monitoring.
- Existing fictional product data remains strictly isolated from provider-reported SQLite observations.
- Observed offers require real provider evidence, but merchant stock and seller reputation are not independently audited.
