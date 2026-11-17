# Price Engine: Phases 1–3

Python 3.11+ standard-library backend core. No frontend. No external API calls are enabled by default.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Included

- Typed adapter contract and normalized observations
- Fail-closed router, per-source token bucket, circuit breaker, bounded retry
- Strict INR integer-paisa parsing and quarantine anomaly checks
- SQLite WAL/foreign keys, append-only history, idempotent writes, attempts table
- Disabled retailer configuration template; no unauthorized scraping

## Integration requirements before live use

This is an executable **backend foundation**, not a certified production deployment. Real authorized API adapters, permitted HTML adapters, policy evaluation, persistent rate-limit/breaker state across workers, scheduler with Retry-After, source identity verification, secure credential management, attempts logging, migrations/versioning, operational metrics, concurrency tests, and actual live-source contract tests must be implemented before production deployment. The router's in-memory breakers and token buckets only coordinate a single process. `PriceStore.persist` assumes a trusted validation call; integrate it behind a single ingestion service that performs validation and transactional persistence. Schema constraints alone cannot validate retailer identity. The source record ID must be stable across retries and distinct for new observations; never derive it from the ingestion attempt time.

`config/selectors.json` intentionally disables all network sources. Never enable extraction without reviewing authorization, terms, robots rules, and access limitations. Never circumvent CAPTCHA or access denial.

## Integrated offline ingestion demo

From the `backend/` directory after cloning the repository:

```bash
python -m pip install -r ../requirements.txt
python -m unittest discover -s tests -v
python -m price_engine.demo --db price_engine.sqlite3
python -m price_engine.demo --db price_engine.sqlite3
```

The second run must print `inserted: False` because the fixture has a stable source record ID. The example is **not a live Croma price**. `tests/fixtures/croma_product.html` is a synthetic example, not a captured retailer page.

The HTML adapter `StructuredHTMLClient` has disabled live network access by default; enable it only after documenting site permission and testing the retailer's current policies. It requires a matching SKU/productID/MPN in structured metadata; it does not guess product identity from a title. For production, replace the synchronous `requests` call with a nonblocking transport, pin DNS resolution across connect to prevent rebinding, implement Retry-After parsing, persistent rate limits, durable attempts logging, and approved API adapters. No live source has been validated yet.
