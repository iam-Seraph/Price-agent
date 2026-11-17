# Price-Checker & Deal Tracker Agent

Python learning project with three **separate** workflows: mock-data ReAct AI, a standalone live URL price checker, and a hardened SQLite backend with a local read-only dashboard.

> **Status:** Phase 4 dashboard and backend hardening are merged into `main` via [PR #1](https://github.com/iam-Seraph/Price-agent/pull/1) (merge `89f6b0fa`). **Not production-ready**; no automatic retailer tracking. See [AUDIT.md](AUDIT.md) for the complete findings and evidence.

## Components

| Component | Command or location | Source of prices | Limits |
| --- | --- | --- | --- |
| ReAct agent | `price_agent.py` | Fictional USD catalog and temporary JSON history | Groq/OpenAI optional; **not connected** to SQLite |
| Standalone URL checker | `live_price.py` | Structured metadata from a permitted HTTPS product URL | Can report price unavailable; **no history** |
| Backend engine | `backend/price_engine/` | Offline fixtures; opt-in approved adapters | Retailer network ingestion disabled by default |
| Phase 4 dashboard | `backend/price_engine/dashboard.py` | Existing local SQLite history | Read-only; no manual fetch or running scheduler by default |

The backend uses **integer INR paisa** for prices. The legacy root agent uses **fictional USD**, so their values and verdicts must not be mixed.

## Requirements and setup

Use **Python 3.11+** for the whole repository. In VS Code, open this repository and choose **Terminal → New Terminal**. In PowerShell from the repository root:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements-dashboard.txt
```

For macOS/Linux activate with `source .venv/bin/activate` instead. The dashboard dependencies include the root application requirements. Install `backend/requirements-dev.txt` separately to run pytest, mypy and property-test tooling.

## Start the Phase 4 dashboard (offline)

From the repository root after installation:

```powershell
cd backend
python -m unittest discover -s tests -v
python -m price_engine.demo --db price_engine.sqlite3
python -m price_engine.dashboard --db price_engine.sqlite3 --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Keep the terminal open and press **Ctrl+C** to stop it.

- The demo creates a sample database from a **local synthetic HTML fixture**, not an actual retailer quote. Rerunning it normally prints `inserted: False` because the demo observation ID is fixed.
- The dashboard reads an **existing** DB; it cannot create or migrate one. SQLite connections use read-only `mode=ro`, `PRAGMA query_only=ON` and parameterized SQL. Append-only history is never written by the UI.
- It displays active listings with `VALID_PRICE`, `OUT_OF_STOCK`, `QUARANTINED` or `UNAVAILABLE` states, recent sparklines, and stale markers (older than 24 hours). Browser data refresh is every 30 seconds.
- There is **no product-registration UI, manual retailer fetch, or running polling scheduler**. The scheduler health says `NOT_CONFIGURED` by default.
- This server has **no authentication**. Only bind it to `127.0.0.1`; do not expose it publicly.

### Dashboard routes

| Route | Description |
| --- | --- |
| `GET /` | Responsive local UI |
| `GET /api/listings?limit=50&offset=0` | Active listings, latest validated state, exact paisa/rupee display, 30-day trends |
| `GET /api/listings/{listing_id}/history?days=30` | Accepted in-stock history, exact total/count/low and rounded display average |
| `GET /api/health` | Read-only database check and scheduler status |

See [backend/README.md](backend/README.md) for endpoint details and implementation.

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

```powershell
# From repository root
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m unittest discover -s tests -v
python -m pytest -q tests
python -m mypy --strict price_engine
python -m benchmarks.loopback
```

**Previously observed release evidence:** 34 backend tests passed with unittest/pytest; Python compilation and whitespace checks passed. These are **historical local results**, not newly verified GitHub CI. Strict mypy and Hypothesis property testing were **not run** in that environment; performance non-regression was not proven. The benchmark uses localhost synthetic latency/errors, not retailer traffic. See [AUDIT.md](AUDIT.md) for the exact evidence and limitations.

## Repository map

```text
Price-agent/
├── README.md                  # Unified quick start and project status
├── AUDIT.md                   # Detailed findings, evidence and release history
├── .env.example               # Placeholders, never real API keys
├── .gitignore
├── requirements.txt
├── price_agent.py             # Root mock-data ReAct workflow
├── live_price.py              # Standalone URL extractor
├── price_history.json         # Reference fixture, not SQLite history
└── backend/
    ├── README.md              # Detailed architecture and API
    ├── migrations/001_initial.sql
    ├── config/selectors.json  # Integrations disabled by default
    ├── requirements-dashboard.txt
    ├── requirements-dev.txt
    ├── price_engine/          # Router, adapters, SQLite, dashboard
    ├── benchmarks/loopback.py
    └── tests/
```

## Security and remaining work

- Keep keys in local `.env` or a secure secrets manager, never in GitHub, screenshots, logs or issues. Rotate any previously exposed key. A `.gitignore` cannot erase already committed secrets.
- Current limitations include missing authorized retailer API adapters/contract tests; DNS-pinned SSRF-safe connections; cross-process rate/circuit coordination; ingestion-attempt logging and observability; durable migration versions; the root ReAct-to-SQLite integration; authenticated/TLS-protected public deployment; independently verified mypy/Hypothesis and real load testing.
- Existing database schema and append-only history triggers were unchanged by the hardening release. Never enable third-party retailer ingestion based only on fixture tests.

**Documentation roles:** This root README consolidates what users need to install, run, test and assess project maturity. [backend/README.md](backend/README.md) is the detailed API/architecture guide. [AUDIT.md](AUDIT.md) is the complete historical audit and evidence record; it is retained rather than deleting findings.

## Release history

- **2026-11-18:** Phase 2 hardening + Phase 4 dashboard merged from `audit/hardening` to `main` through [PR #1](https://github.com/iam-Seraph/Price-agent/pull/1); merge commit `89f6b0fa343502797ba697252afb021497ac0b66`. Five branch commits, 28 changed files, no force-push.
