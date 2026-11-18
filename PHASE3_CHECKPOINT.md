# Phase 3 — Loops 21–30: real-price dashboard bridge

This checkpoint builds on the merged, source-attributed Phase 1 and Phase 2 pipelines. New functionality is read-only web presentation; no AI-generated or fictional product is inserted into the verified offer tables.

--- LOOP [21]: Latest-source offer projections ---
Show actual latest price, source provenance, merchant and stock status from SQLite, rather than a fabricated summary.

--- LOOP [22]: Bounded provider-history query ---
Add safe, parameterized history retrieval limited to 1–365 days and at most 1,000 rows.

--- LOOP [23]: HTTP read APIs ---
Expose real-offer and per-offer history/analysis routes from the local FastAPI app.

--- LOOP [24]: Evidence-level metrics ---
Calculate product and observation counts from persisted rows; never substitute virtual-catalog SKU totals.

--- LOOP [25]: Grounded HTML interface ---
Create a standalone dashboard page that renders the stored provider data and preserves an explicit empty state.

--- LOOP [26]: Browser history visualization ---
Use locally served JavaScript to chart actual persisted values and render deterministic deal checks. External content is inserted using DOM textContent, not HTML.

--- LOOP [27]: Responsive CSS ---
Use a small local stylesheet, keyboard focus indicators and mobile-adaptable layout.

--- LOOP [28]: Source status API ---
Expose stored event counts and timestamps for the dashboard. The API reports live-provider connection status as false because no continuous connection is maintained.

--- LOOP [29]: Application integration ---
Mount /verified and /api/verified/ routes in the existing local-only workspace app without changing legacy routes.

--- LOOP [30]: Regression tests ---
Test the empty state, latest stored offer, history, budget mismatch and static assets.

## How to run

1. Install packages from the repository root:
```bash
python -m pip install -r backend/requirements-workspace.txt -r backend/requirements-dev.txt
```
2. For the same database used by your actual SerpApi ingestion, initialize the pre-existing dashboard tables **without inserting demo observations**:
```bash
python -c "from backend.price_engine.storage import PriceStore; PriceStore('tracker.sqlite3','backend/migrations/001_initial.sql').close()"
```
3. Run the local workspace:
```bash
cd backend
python -m price_engine.workspace --db ../tracker.sqlite3 --workspace-db workspace.sqlite3 --host 127.0.0.1 --port 8000
```
4. Open `http://127.0.0.1:8000/verified`. A zero-record view is expected until you ingest real provider observations with `python real_price_agent.py --query "laptop" --budget 60000 --currency INR --db tracker.sqlite3` from the repository root. A private `SERPAPI_KEY` is required for that command.

### Security and accuracy boundaries
- The new endpoints are read-only, local-development features with no public authentication. Do not expose the workspace server on a public interface.
- Provider-reported prices have timestamps, source identifiers and SHA-256 fingerprints. They are not independently audited retail quotations.
- Stock and seller-rating evidence are separately tracked. Missing evidence fails closed to NO_ALERT.
- The legacy `/intelligence` fictional simulator remains explicitly labeled and isolated, for test compatibility; `/verified` shows only real persisted offers.
- All prior commands remain supported. Live API access and browser visual tests require separate verification.
