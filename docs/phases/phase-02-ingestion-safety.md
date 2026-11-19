# Phase 2 — Loops 11–20: provider ingestion safety

This checkpoint builds directly on the **merged** Phase 1 foundation. It does not remove existing CLI entry points or rewrite historical source records.

## Audit and changes

--- LOOP [11]: Anchor provider currency labels ---
Require a leading explicit INR, USD, rupee or dollar label instead of detecting currency markers anywhere in a free-form string. Avoid misreading installment and promotion strings as retail prices.

--- LOOP [12]: Correct strict expression escaping ---
Use a valid anchored regular expression for the exact supported provider-price label forms. Validate this parser through regression tests.

--- LOOP [13]: Validate source URL characters and ports ---
Reject control characters, invalid port specifications and malformed HTTPS evidence addresses before inserting provider data.

--- LOOP [14]: Deduplicate provider results ---
Ensure repeated shopping entries within a single provider response never create multiple observations.

--- LOOP [15]: Enforce merchant identity ---
Do not accidentally treat null or non-string seller sources as legitimate merchant names.

--- LOOP [16]: Reject invalid retailer product identifiers ---
Do not stringify a boolean product ID into an apparently stable identifier. Use the explicitly attributed URL fingerprint when no valid provider identifier is given.

--- LOOP [17]: Bound provider payload processing ---
Refuse JSON responses exceeding 2 MiB before decoding into Python objects.

--- LOOP [18]: Safe bounded retries ---
Retry transient connection failures and server errors with 0.25, 0.5 and 1.0 second exponential backoff; never retry access-denied or throttled requests. No anti-bot or access-control bypass.

--- LOOP [19]: Regression tests ---
Add tests for strict currency, metadata validation, deduplication, transient retries and 429 no-retry behavior.

--- LOOP [20]: Checkpoint integration ---
Publish the updated checkpoint, preserve original commands and run the three GitHub Actions regression suites.

## Commands

```bash
python -m pip install -r backend/requirements-workspace.txt -r backend/requirements-dev.txt
python -m unittest discover -s backend/tests -p 'test_verified_pipeline.py' -v
python real_price_agent.py --list --db tracker.sqlite3
```

For actual provider queries, configure a private SerpApi key as a Codespaces secret or in an untracked root `.env`. The code does not import fictitious prices or invent shopping results.

## Readiness

**Scope implemented:** hardened SerpApi response validation, bounded retries, safe evidence links, deduplication, existing SQLite analysis, and test coverage.

**Not yet implemented:** automatic scheduled ingestion, persistent watchlists, outbound notifications, unified real-price dashboard, multiuser accounts and live end-to-end service verification.
