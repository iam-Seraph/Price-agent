# Phase 10 checkpoint — Loops 91–100: security, diagnostics and final audit

The cumulative 100-loop plan includes these ten implemented improvement checkpoints, additive to Phases 1–9.

--- LOOP [91]: Database quick integrity check ---
Run SQLite PRAGMA quick_check(1) on demand to detect structural database problems.

--- LOOP [92]: Relational integrity ---
Detect foreign-key violations without exposing their underlying row details in the local HTTP API.

--- LOOP [93]: Historical evidence invariants ---
Audit positive prices, provider-only provenance and impossible future timestamps; fail closed instead of approving corrupted history.

--- LOOP [94]: Operator diagnostics CLI ---
Run python price_audit.py --db tracker.sqlite3. The script emits JSON and returns a nonzero exit status for failed or unavailable data.

--- LOOP [95]: Local diagnostics endpoint ---
GET /api/verified/diagnostics returns aggregate evidence-integrity details and single-operator status, without contacts, keys or file paths.

--- LOOP [96]: Browser security headers ---
Verified UI/API responses use no-store, no-sniff, anti-framing and referrer controls; the verified page has a self-origin Content Security Policy.

--- LOOP [97]: Dashboard JavaScript syntax gate ---
The main workspace CI checks verified.js as well as the existing Intelligence Studio JavaScript files.

--- LOOP [98]: Offline security and readiness regression ---
Test empty and populated databases, simulated impossible future evidence, unavailable database, CLI status, diagnostics, headers and cross-site protections.

--- LOOP [99]: Multi-user readiness boundary ---
Document the single-operator design and a concrete authentication/tenant-isolation migration plan in TENANCY_DESIGN.md. A multi-user product is NOT implemented.

--- LOOP [100]: Final audit and merge gate ---
Run GitHub Actions, inspect CI status and tracked-file diff, and merge only if checks pass. Record unverified provider behavior and production blockers.

## Run locally

- From the repository root: python price_audit.py --db tracker.sqlite3
- From the backend directory: python -m pytest -q tests
- Visit http://127.0.0.1:8000/api/verified/diagnostics on the local workspace server.

## Scope, limitations and release evidence

- Verified: Source-attributed stored-data processing, deterministic deal checks, regression tests and local operational safeguards, conditional on passing CI.
- Not independently verified: Real-time retailer price/stock correctness, merchant trust, anomaly interpretation or price prediction.
- Not completed: Public hosting, production authentication, multi-user authorization, privacy controls, real provider contract testing, payment/purchase functionality.
- CI uses offline fixtures; they never become live catalog fallback.
- Secrets must live in private environment variables, never in Git.
- The one hundred loop labels are engineering checkpoints, not a claim of one hundred autonomous production jobs.

See PHASE9_CHECKPOINT.md for historical evidence and TENANCY_DESIGN.md for the explicit single-operator security boundary.
