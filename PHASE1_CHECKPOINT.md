# Phase 1 checkpoint — source-grounded architecture audit

Base commit: `f3a06c10bc88b65efce1cc7da82189be014c383b`.
Development branch: `feat/phase1-verified-prices`.

## Existing implementation

- `src/price_agent.py` uses a synthetic USD catalog and temporary JSON observations; it does **not** use the backend's SQLite price history.
- `backend/price_engine/storage.py` stores append-only INR observations and supports exact 30-day aggregation for existing retailer listings.
- `backend/price_engine/product_lookup.py` supports SerpApi but deliberately falls back to DummyJSON and synthetic examples; these must never be accepted as verified offer prices.
- `backend/price_engine/workspace.py` offers a local read-only dashboard, upload demos and a labeled fictional Intelligence Studio.
- `backend/migrations/001_initial.sql` restricts its original price history to INR. Rewriting that in place would risk existing data and compatibility.

## Phase 1 invariant

This checkpoint adds a **separate, compatible, provenance-aware offer ingestion pipeline in the existing SQLite database**. The original INR history tables and public commands remain intact. Only provider-reported responses carrying a numeric price, explicit currency, stable identity and trustworthy source metadata can enter the new offer tables. No fake catalog data, DummyJSON fallbacks or AI-generated prices may enter the trusted tables.

Real provider observations are **provider-reported, not independently verified retail quotes**. Source attribution and fetch timestamps are retained; the system must fail closed on missing identity, currency, stock or seller evidence. A model may explain decisions but cannot override deterministic pricing rules.

## Ten-loop plan

1. Audit and establish non-regression constraints.
2. Implement exact INR/USD minor-unit parsing.
3. Define strict provider-offer types and safe identity handling.
4. Add a real SerpApi-only provider adapter with dependency injection.
5. Create additive SQLite schema for source-linked offer observations.
6. Implement atomic, idempotent persistence.
7. Implement 30-day and all-time price analysis with deterministic safeguards.
8. Expose DB-only agent tools; no guessed facts.
9. Add an end-to-end command-line ingest/analyze flow.
10. Add tests, automated checks and checkpoint documentation.

## Scope boundary

No Groq live call, retailer scraping, unattended scheduling, account registration, alert delivery or public deployment is claimed in loops 1–10. Those need later loops and live-provider credentials. The existing fictional Intelligence Studio remains clearly separate until a replacement frontend is ready.

## Implemented Phase 1 checkpoint commands

Install the backend and developer dependencies from the repository root:

```bash
python -m pip install -r backend/requirements-dev.txt
python -m unittest discover -s backend/tests -p 'test_verified_pipeline.py' -v
```

For real provider search, configure a **new** `SERPAPI_KEY` privately as a Codespaces secret or in the ignored root `.env` (do not commit this file):

```bash
python real_price_agent.py --query "laptop" --budget 60000 --currency INR --db tracker.sqlite3
```

Read persisted offers without contacting SerpApi (copy a real offer ID from this result to analyze it with `--offer-id`):

```bash
python real_price_agent.py --list --db tracker.sqlite3
```

The first command requires a real provider key and authorized SerpApi plan. `--explain` is optional and additionally requires a private Groq API key. The default decision is deterministic Python, not model output. No network calls are made for offline reports.

## Concrete checkpoint files

- `backend/price_engine/verified/money.py` — exact INR/USD minor units and explicit currency enforcement.
- `backend/price_engine/verified/types.py` — validated offer identity, safe display-only URL and evidence hashes.
- `backend/price_engine/verified/provider.py` — SerpApi-only fixed-endpoint adapter; no synthetic fallback.
- `backend/migrations/003_verified_offers.sql` — additive, append-only provenance-aware schema.
- `backend/price_engine/verified/store.py` — event-idempotent transactional ingestion.
- `backend/price_engine/verified/analysis.py` — 30-day unique-day windows, exact rule checks and all-time low.
- `backend/price_engine/verified/tool_agent.py` — strictly read-only SQLite tools for optional Groq explanations.
- `backend/price_engine/verified/cli.py`, `real_price_agent.py` — new real-data CLI.
- `backend/tests/test_verified_pipeline.py` — offline provider and database regression tests.
- `.github/workflows/verified-phase1.yml` — Phase 1 CI checks.

## Completion criteria and incomplete scope

| Goal | Phase 1 checkpoint status |
| --- | --- |
| No fake price ingestion | Implemented in new provider pipeline; original demo paths are unchanged and isolated |
| Explicit INR/USD monetary units | Implemented in new provider pipeline |
| Source attribution and immutable observations | Implemented; provenance is **provider-reported** |
| SQLite history windows and all-time low | Implemented for new provider tables |
| Groq tool calls querying stored data | Implemented as optional read-only explanation layer; live call not verified |
| Live product offer verification | Not independently verified; provider-reported only |
| Automatic scheduling, retailer URL crawling, and alerts | Not implemented in Phase 1 |
| New UI replacing the Intelligence Studio | Not implemented; fictional Studio remains segregated |
| Multi-user authentication and public hosting | Not implemented; do not expose unauthenticated local dashboard publicly |

## Loop changelog

1. Captured baseline architecture and non-regression constraints.
2. Added exact INR/USD price normalization.
3. Added strict provider and identity datatypes.
4. Added fixed-host SerpApi adapter without demo fallback.
5. Added backwards-compatible SQLite offer/history migration.
6. Added atomic, idempotent ingestion.
7. Added historical deal calculation that fails closed on missing evidence.
8. Added read-only, budget-locked SQLite tools for Groq explanations.
9. Added real-provider CLI and existing-record analysis.
10. Added offline regression tests, GitHub Actions and updated documentation.
