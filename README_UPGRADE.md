# Price Agent — Data Workspace Upgrade

This is an **overlay**, not a replacement repository. Copy the `backend/` directory in this archive over the existing `backend/` directory. Existing source files are kept. Only two existing files are replaced: `backend/price_engine/templates/dashboard.html` and `backend/price_engine/templates/catalog.html`, to add the new workspace navigation link. The original `price_engine.dashboard`, original catalog routes, and root `price_agent.py` are unchanged. A separate `price_agent_workspace.py` entry point adds the lookup tool to the existing ReAct agent without modifying its safety checks.

## Run on Windows / VS Code

1. Stop the current server with `Ctrl+C`.
2. Extract this archive into the **root** of your existing `Price-agent` clone (the folder containing `price_agent.py`). Confirm the archive's `backend/` files merge with your existing `backend/` directory, not a nested `backend/backend` folder.
3. From the existing clone root in PowerShell:

```powershell
python -m pip install -r backend/requirements-workspace.txt
cd backend
python -m price_engine.workspace --db demo_fresh.sqlite3 --workspace-db workspace.sqlite3 --host 127.0.0.1 --port 8000
```

Visit `http://127.0.0.1:8000/workspace`. The original `/` and `/catalog` still work. **Do not rerun** `python -m price_engine.demo` against an already populated history database.

## Optional Google Shopping integration

Edit the **repository-root** `.env` file (create it if missing):

```dotenv
SERPAPI_KEY=your_real_serpapi_key
```

Do not commit `.env`. Without the key, the research tool queries the **DummyJSON sample API**; if offline, it uses the **bundled fictional demo dataset**. Only a configured SerpApi key enables Google Shopping results. This does not bypass retailer restrictions or guarantee current prices, availability, review accuracy or API availability. API usage can have charges.

The product lookup function is `price_engine.product_lookup.lookup_product(query)`. The HTTP tool endpoint is `POST /api/workspace/agent/lookup` with JSON `{"query":"wireless headphones"}`. This is a **read-only research tool** for an agent and the workspace UI. The included `price_agent_workspace.py` also registers it with the existing root ReAct tool dispatcher. Run `python price_agent_workspace.py --product "headphones" --budget 300` from the repository root after configuring the existing `AI_PROVIDER` key. The legacy agent still uses USD budgets and mock history, so live INR research cannot certify a deal. Neither entry point inserts unverified prices into `price_history`.

## Upload schema

Supported: `.csv`, `.json` array or `{ "products": [...] }`, and `.xlsx` first worksheet. File size limit **2 MiB**, max **1,000** rows. Required fields:

- `name`: product name (text, 1–180 characters)
- `retailer`: seller/source (text, 1–100 characters)
- `price`: numeric **INR rupees**, up to two decimal places

Optional fields:

- `currency`: `INR` (other currencies rejected to prevent accidental mixing)
- `availability`: `IN_STOCK`, `OUT_OF_STOCK`, or `UNKNOWN` (default)
- `rating`: number from 0 to 5
- `review_count`: nonnegative integer
- `specs`: JSON object (for CSV/Excel, a JSON-formatted string in the cell)
- `product_url`: HTTPS URL, shown as data only, never fetched by the backend

Example CSV: `backend/examples/sample_upload.csv`.

Example JSON:

```json
{"products":[{"name":"USB-C Charger 45W","retailer":"My Store","price":1299.0,"currency":"INR","availability":"IN_STOCK","rating":4.4,"specs":{"power":"45 W"}}]}
```

Uploaded records live in `backend/workspace.sqlite3` by default. They are **not** imported into the verified append-only history. Demo and uploaded datasets can be switched instantly; uploads persist across restarts. This local-only server is **not** multi-user or production-ready: no authentication, quotas per user, or public hosting support.

## Files in this overlay

| File | Role |
| --- | --- |
| `price_agent_workspace.py` | Optional existing ReAct agent entry point with live product research tool |
| `backend/price_engine/workspace.py` | FastAPI extension, upload and dataset/agent API routes, server entry point |
| `backend/price_engine/workspace_data.py` | Validation, CSV/JSON/XLSX parsing, isolated SQLite storage, source switching |
| `backend/price_engine/product_lookup.py` | SerpApi Google Shopping / DummyJSON / offline tool |
| `backend/price_engine/data/demo_products.json` | 8 bundled synthetic products |
| `backend/price_engine/templates/workspace.html` | New UI page, matching existing dashboard styling |
| `backend/price_engine/static/workspace.js` | Demo/upload/switch/lookup interactions |
| `backend/price_engine/static/workspace.css` | Small additive styles on existing dashboard.css |
| `backend/price_engine/templates/dashboard.html` | Existing page, with Data & Agent nav link added |
| `backend/price_engine/templates/catalog.html` | Existing page, with Data & Agent nav link added |
| `backend/requirements-workspace.txt` | Installs existing dashboard deps + python-multipart and openpyxl |
| `backend/workspace-env.example` | Optional SerpApi configuration example |
| `backend/examples/sample_upload.csv` | Upload example |
| `backend/tests/test_workspace_upgrade.py` | Offline integration and validation tests |

## Verify

```powershell
# From backend/ with the venv active:
python -m pytest -q tests/test_workspace_upgrade.py
```

Tests were run on this overlay independently. The entire original repository's test suite was **not** run here because the existing repository could not be cloned into the local build environment.

### Security and provenance

Only run on localhost (`127.0.0.1`). Host-header validation helps prevent DNS-rebinding access and cross-origin browser writes are rejected. Uploaded datasets are not authenticated or safe for public hosting. Product lookups only contact fixed API hosts; provider data is unverified research, not approved price history. Uploaded files have a 2 MiB cap, 1,000 accepted product row cap, and bounded column/scan limits. No keys or uploaded datasets are checked into source control.
