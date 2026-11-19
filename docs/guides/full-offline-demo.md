# Full Price Agent offline demo

This mode supplies an interactive, **synthetic equivalent** for every major feature without Google Shopping, Groq, OpenAI, email, Telegram, internet, or real keys. This is educational simulation, **not real retailer evidence**.

## Start from repository root

Install Python 3.11+ dependencies once while online, then work without connectivity:

~~~bash
python -m pip install -r backend/requirements-workspace.txt -r backend/requirements-dev.txt
python price_demo.py
~~~

Open **http://127.0.0.1:8000/demo**. The server binds to loopback only. No API keys are required. Run a complete in-memory workflow with temporary databases, or the full test suite:

~~~bash
python price_demo.py smoke
python scripts/full_check.py
~~~

## Offline feature coverage

| Feature | Available offline equivalent | What is not simulated as real |
| --- | --- | --- |
| Google Shopping search | Bundled fictional products and sellers | No Google/retailer API calls or current market prices |
| Product comparisons | Separate fictional listings with accurate INR arithmetic | No product-equivalence guarantee |
| Price history and deal checks | 14 simulated historical observations per offer and heuristics | No evidence of genuine discounts or seller trust |
| AI explanations | Clearly labeled deterministic explanation | No Groq/OpenAI model inference |
| Natural-language commands | Supported comparison and watch grammar | No unrestricted autonomous actions |
| Price watch | Explicitly saved demo watch and manual polling cycle | No real background retailer monitoring |
| Email/Telegram | Fake queued alerts and local SIMULATED_SENT receipts | No external messages, credentials or actual recipients |
| Learning | Explicit preference votes, opt-in, pause and erase | No model weight updates, no automatic learning from arbitrary sites |
| Catalog | Bundled fictional catalog | Not the genuine Open Food Facts export |
| Workspace | Local CSV/JSON/XLSX upload and forced offline product lookup | No network lookup |
| Intelligence Studio | Existing fully fictional virtual product simulator | No retailer inventory |
| Diagnostics and config | SQLite audit and offline key-free status | No live API credential test |

The older read-only history and imported-catalog pages are still accessible through the navigation; they can be empty until their separate datasets are populated.

## Isolation and privacy

The demo creates ignored .price-agent-demo/ data files: synthetic_demo.sqlite3, legacy_demo.sqlite3 and workspace_demo.sqlite3. The core simulator uses its **own schema** and rejects a database containing unrelated real-price tables. All its observations are explicitly marked DEMO_FIXTURE; none are inserted into the real verified_offer_observations table or labeled PROVIDER_REPORTED.

The demo server explicitly blocks real provider searches at POST /api/verified/search (HTTP 409). Even if SERPAPI_KEY is set, workspace lookup uses bundled offline fixtures only. The UI and APIs never call Groq, SerpApi, external SMTP/Telegram or product URLs. All writes require same-origin requests, and the server has no production authentication: keep it on 127.0.0.1.

## Walkthrough

1. Search **headphones** with budget 4000, inspect a fictional listing and its price history.
2. Create a headphones watch at INR 4000 using the simulated email or Telegram channel.
3. Click **Run one offline monitoring cycle**. This advances all synthetic quotes and queues matching fake alerts.
4. Click **Simulate alert delivery** to write local receipts only.
5. Enable preferences; select and prefer one product, avoid another, then compare again. Personalized ordering changes, but objective price comparison and deal checks remain unchanged.
6. Test **compare headphones under ₹4000** or **watch headphones below ₹4000** in the command assistant.
7. Open the offline product catalog and the links to the local data workspace and Intelligence Studio.

All fake history and preference votes persist across restarts under .price-agent-demo/. Manual simulation is capped at 100 cycles to avoid runaway storage. To begin fresh, stop the server and intentionally remove **only** .price-agent-demo/; never remove your real tracker.sqlite3.

## Prerequisites and limitations

Installing Python packages, acquiring real providers' API keys, and downloading the actual Open Food Facts bulk catalog require internet at some point. The demo cannot independently prove that live Google, Groq, SMTP or Telegram works. It does provide an interactive, validated stand-in for these features with **zero actual network usage**.
