# Price Agent

**Local-first Python price research and experimentation toolkit.** This repository contains a source-attributed SerpApi/SQLite offer pipeline, price history and watch tools, an optional Groq explanation layer, an Open Food Facts product-identity catalog, and separate **clearly labeled mock/simulated** demos.

**Status — 19 November 2026:** Engineering checkpoints **1–100 (Phases 1–10)** are merged into `main`. These are development milestones, **not 100 continuously running autonomous agents**. Offline GitHub Actions regression workflows passed for the Phase 10 merge. **Not production-ready, not multi-user, and not an independently verified retailer-price service.**

## Start here — local verified-offer dashboard

Requires **Python 3.11+**. From the repository root:

~~~bash
python -m venv .venv
# Activate: Windows PowerShell: .\.venv\Scripts\Activate.ps1
#          macOS/Linux:       source .venv/bin/activate
python -m pip install -r backend/requirements-workspace.txt -r backend/requirements-dev.txt

# Once per new legacy history database (do not delete or reseed existing data):
python -c "from backend.price_engine.storage import PriceStore; PriceStore('tracker.sqlite3','backend/migrations/001_initial.sql').close()"

cd backend
python -m price_engine.workspace --db ../tracker.sqlite3 --workspace-db workspace.sqlite3 --host 127.0.0.1 --port 8000
~~~

Open the **local-only** pages:

| URL | Data provenance | Function |
| --- | --- | --- |
| `/verified` | Source-attributed, *provider-reported* offers saved in SQLite | Offer lookup, saved research, historical intelligence, watches, assistant planner and diagnostics |
| `/` | Local legacy demo/history | Read-only historical observation dashboard |
| `/catalog` | Imported Open Food Facts identities, **no retailer prices** | Product catalog search |
| `/workspace` | Synthetic/uploaded datasets; optional provider research | Personal CSV/JSON/XLSX workspace |
| `/intelligence` | **Entirely fictional** virtual product data | Intelligence Studio UI simulation |

No retailer requests or monitoring workers start merely by opening the dashboard. The server is unauthenticated: **bind only to loopback (127.0.0.1)**.

## Configure optional external providers safely

Copy `.env.example` to a local `.env` at the repository root. Set `SERPAPI_KEY` for explicit Google Shopping searches and optionally `GROQ_API_KEY` for model-generated explanations; check the model's current availability and API charges. Never commit `.env`, keys, local databases or downloaded exports. If a key was previously shared in chat, a repository or public logs, **rotate it**.

SerpApi offers are **attributed provider observations**. They are not independently verified stock/merchant/price facts. Missing data must not be replaced with generated prices.

## Root command reference

Run these from the repository root, using the **same** `tracker.sqlite3` for related verified features:

| Command | Purpose |
| --- | --- |
| `python real_price_agent.py --query "headphones" --budget 3000 --currency INR --db tracker.sqlite3` | Request source-attributed provider offers; requires private SerpApi key |
| `python real_price_agent.py --list --db tracker.sqlite3` | Inspect stored offers without provider calls |
| `python price_research.py "headphones" --budget 3000 --currency INR --db tracker.sqlite3` | Compare previously stored offers |
| `python price_intelligence.py OFFER_ID --db tracker.sqlite3 --days 90` | Read recorded daily prices, anomaly heuristics, observed trends and evidence completeness |
| `python price_audit.py --db tracker.sqlite3` | Run on-demand SQLite integrity/provenance diagnostics |
| `python price_watch.py --db tracker.sqlite3 list` | Show explicitly saved watch rules |
| `python price_assistant.py "compare headphones under ₹3000" --db tracker.sqlite3` | Deterministic natural-language comparison (not an unrestricted agent) |
| `python price_agent.py` | Separate **fictional USD** ReAct demo; no real-store certification |
| `python live_price.py --help` | Independent HTTPS URL metadata checker, which may report unavailable prices |

A saved price watch **does not automatically poll**. Start the opt-in worker explicitly with `price_watch.py ... run`; alerts additionally require configured, consented channels, credentials and a separately running `price_alert.py` dispatcher. See [Phase 4](docs/phases/phase-04-price-watches.md) and [Phase 5 alerts](docs/phases/phase-05-alerts.md).

## Verify the complete offline project

Install the workspace and development dependencies (commands above), and install Node.js 22 or newer. Run **one command** from the repository root:

~~~bash
python scripts/full_check.py
~~~

This runs documentation-link checks, all backend **pytest and unittest** regression tests (including an end-to-end mocked source-to-alert smoke test), Python compilation, JavaScript syntax checks and Node worker tests. The same command runs in the workspace CI workflow. It **does not** call live SerpApi/Groq, deliver real notifications, purchase products, prove merchant facts or run production load/security tests.

## Organized repository map

~~~text
Price-agent/
├── README.md                 # Current overview / commands
├── docs/
│   ├── README.md             # Documentation index and release map
│   ├── guides/               # Catalog import, workspace, virtual UI
│   ├── architecture/         # Security and deployment boundaries
│   ├── audits/               # Preserved historical findings
│   └── phases/               # Phase 1–10 development checkpoints
├── backend/
│   ├── README.md             # Python engine and API details
│   ├── price_engine/         # Modules, templates and static files
│   ├── migrations/           # SQLite schemas
│   └── tests/                # Automated tests
├── src/                      # Legacy standalone source modules
├── site/                     # Static project showcase (not live app)
├── data/                     # Mock-data fixtures
├── .github/workflows/        # Continuous integration
├── price_*.py, real_price_agent.py, live_price.py
│                            # Stable, backwards-compatible CLI launchers
└── .env.example              # Safe template; real .env is ignored
~~~

**Documentation:** [all guides and phases](docs/README.md) · [backend details](backend/README.md) · [verified price history (Phase 9)](docs/phases/phase-09-historical-intelligence.md) · [release diagnostics (Phase 10)](docs/phases/phase-10-release-hardening.md) · [single-operator security plan](docs/architecture/single-operator-security.md).

### Boundaries and unfinished work

- Groq-assisted mock ReAct, standalone URL extraction, Open Food Facts catalog, virtual Intelligence Studio, and source-attributed provider prices are **distinct** features: their datasets must not be silently combined.
- Evidence completeness scores describe recorded fields, **not seller trust**; anomaly flags are heuristics, not proof of fake discounts; no future-price prediction is implemented.
- Multi-user authentication, independently checked live retailer truth, production-ready deployment, purchase automation and large-scale catalog performance are **not implemented/verified**.
- Old tutorial references to names such as `PHASE5.md` are historical; use the canonical links under [docs/](docs/README.md). Root Python entry-point filenames intentionally remain stable.
