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
