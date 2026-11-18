# Price Signal Intelligence Studio — Virtual Product Catalog

**New page:** `http://127.0.0.1:8000/intelligence`

This is a local-first interactive **simulation** integrated into the existing FastAPI/SQLite Price Agent workspace. It does **not** replace `/`, `/catalog`, `/workspace`, the SQLite ingestion engine, or the root ReAct agent.

## Quick start (Windows / VS Code)

From your existing Price Agent repository root in PowerShell, after `git pull --ff-only origin main` if your checkout has no conflicting local changes:

```powershell
python -m pip install -r backend/requirements-workspace.txt
cd backend
python -m price_engine.workspace --db demo_fresh.sqlite3 --workspace-db workspace.sqlite3 --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/intelligence`. Use `/workspace` for the previous CSV/JSON/Excel upload or SerpApi/DummyJSON product lookup workflows. Do **not** rerun the original `price_engine.demo` against a populated history database.

## What the UI does

- Three fictional SKU namespaces: neural compute, gaming peripherals, and autonomous robotics. Each contains **1,048,576 possible SKU IDs**, totaling **3,145,728 virtual SKUs**. These are **generated on demand**, not millions of stored records or genuinely distinct hardware designs. Each family has 8 design archetypes and 128 repeating specification profiles per archetype. There are **3,072 distinct modeled specification profiles** across all three families.
- Page navigation materializes at most **24 visible records per request**. The unified browse view interleaves all three families. Browsing sort controls reorder the **current page only**, not the entire virtual SKU namespace. No database of 3 million products is created or loaded into browser memory.
- A same-origin Web Worker parses the natural-language prompt, extracts an explicit currency/budget and minimum VRAM when present, and scores all **distinct specification profiles**. Results are a **heuristic search and ranking simulation**, not an exhaustive search of every SKU ID, a trained AI model, a verified shopping index, or a calibrated match probability. Query filtering is based on generated metadata and explicit numeric constraints.
- Product cards include unique generated SKU IDs, an expanded technical description, invented benchmark, simulated p95 latency, power draw, warranty tier, rating, fake review counts, efficiency and sentiment scores. **All prices and products are fictional.**
- Compare up to four products across datasets. Priorities: balanced, performance, relative value or energy efficiency. The "winner" is determined **only** by transparent formulas over synthetic scores. Performance and latency units can refer to different systems across categories; do not infer objective cross-category superiority.
- Switch USD / EUR / GBP / INR / JPY instantly. Conversion rates are **fixed demonstration values** in `intelligence.js` and `intelligence.worker.js`; they are *not live forex quotes*. The query parser recognizes explicit currency symbols for budget constraints.
- Get a locally generated explanation, export JSON/Markdown comparisons or advice, use `/`, `C` and `D` shortcuts, and view explicitly simulated telemetry.
- The future-launch section and countdown are **concept placeholders**; no official release or real-product launch date is implied. The email form validates locally, stores only a boolean preview flag in localStorage, and **never transmits or retains the email**. This is **not a functioning mailing list**.
- A WebGL2 particle background draws at no more than ~30 frames/sec, caps device pixel ratio, pauses when hidden/offscreen, and falls back to CSS gradients on unsupported devices or when reduced motion is requested.

## Architecture

| Source | Responsibility |
| --- | --- |
| `backend/price_engine/workspace.py` | Same-origin `/intelligence` route within the existing local FastAPI application |
| `backend/price_engine/templates/intelligence.html` | Accessible markup, product-card template, two native modal dialogs, local assets |
| `backend/price_engine/static/intelligence.css` | Responsive glass-inspired UI, no CSS framework or external fonts |
| `backend/price_engine/static/intelligence.js` | UI state, on-demand rendering, simulated WebGL2, comparison, exports, keyboard/accessibility, local preview |
| `backend/price_engine/static/intelligence.worker.js` | Deterministic generators, constraints and ranked synthetic profiles off the main thread |
| `backend/tests/test_intelligence_studio.py` | FastAPI routes, original navigation and static-asset regression checks |
| `backend/tests/test_intelligence_worker.cjs` | Generator determinism, hard filters, FX rules, page boundaries and worker performance regression |

The original `workspace.sqlite3` database remains solely for previously implemented demo/upload workflows. The original price history is read-only through `ReadOnlyHistory`. The virtual Intelligence Studio neither imports nor inserts into either database. It makes **no external API requests**; the separate `/workspace` product lookup feature can call SerpApi when configured.

## Test and audit

```powershell
# From repository root
python -m pip install -r backend/requirements-workspace.txt -r backend/requirements-dev.txt
cd backend
python -m pytest -q tests
cd ..
node --check backend/price_engine/static/intelligence.js
node --check backend/price_engine/static/intelligence.worker.js
node --test backend/tests/test_intelligence_worker.cjs
```

Browsers should be tested manually on the target OS/GPU before deployment. The local smoke check exercised the application in a headless Chromium DOM harness with an equivalent simulated Worker transport; full browser/host networking and real GPU driver behavior were not benchmarked. The comparison, modal, search and mobile layout operated without page errors under that harness.

## Real production requirements (not implemented)

This is a **high-fidelity, performance-conscious prototype, not a production commerce service**. Before public deployment, add user accounts, authentication and authorization, opt-in mail delivery with verified consent, a rate-limited API, real inventory and price feeds with provenance/freshness checks, live currency FX with source timestamps, server-backed search indexes for actual products, error reporting, accessibility/device testing, privacy policies, CSP review, abuse prevention, and load testing. Never describe virtual products as purchasable inventory.
