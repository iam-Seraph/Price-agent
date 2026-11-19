# Phase 9 checkpoint — Loops 81–90: bounded historical intelligence

Phase 9 is read-only historical analysis of **real persisted provider observations**. No new provider request, synthetic quote, prediction or automatic purchase is performed by these calculations.

--- LOOP [81]: Daily observed UTC series ---
Aggregate only recorded in-stock provider prices into daily lower medians. Gaps stay gaps.

--- LOOP [82]: Bounded history ---
Use at most 1,000 newest observations within an explicit UTC lookback of 1–365 days, with metadata warning about truncation.

--- LOOP [83]: Fail-closed anomaly rules ---
Require a fresh, provider-reported, in-stock current observation and at least 10 earlier observed days before applying fixed drop/rise heuristics.

--- LOOP [84]: Evidence completeness ---
Expose a transparent six-check 0–100 completeness score. Never call it seller trust, safety, authenticity or reputation.

--- LOOP [85]: Observed trend ---
Compare medians in two seven-day periods only when each has at least three recorded days; never forecast future prices.

--- LOOP [86]: Read-only local REST API ---
Provide `GET /api/verified/offers/{offer_id}/intelligence?days=90` with series, anomaly, trend and evidence.

--- LOOP [87]: Read-only operator CLI ---
Provide `python price_intelligence.py OFFER_ID --db tracker.sqlite3 --days 90`.

--- LOOP [88]: Dashboard explanation ---
Show observed daily history, heuristic anomaly signal, evidence completeness and trend with explicit source limitations.

--- LOOP [89]: Offline integration and edge cases ---
Test sparse history, unknown stock, artificial out-of-stock lows, as-of windows, currency provenance, UTC validation, API and CLI reads.

--- LOOP [90]: Checkpoint and release gate ---
Run workspace and verified test workflows on the phase PR, verify successful checks, inspect the diff and then merge.

## Interpreting evidence

- The score is about **record completeness only**, not a recommendation to trust or buy from a seller.
- An anomaly flag is not proof of manipulation; the provider could report changing variants or availability.
- Every offer retains its provider identity; different product IDs are never treated as equivalent.
- A missing day is not estimated or interpolated.
- More than 1,000 observations in the requested range may be truncated; API reports this.
- Local development is loopback-only; production needs authentication and deployment hardening.

## Commands

```bash
python price_intelligence.py YOUR_64_CHAR_OFFER_ID --db tracker.sqlite3 --days 90
cd backend
python -m pytest -q tests/test_verified_intelligence.py
```
