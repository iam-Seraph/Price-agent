# Price Agent — Phase 0–4 hardening and dashboard audit

**Current GitHub release state (verified 2026-11-18):** Phase 2 hardening
and the Phase 4 read-only dashboard were merged through
[PR #1](https://github.com/iam-Seraph/Price-agent/pull/1). Documentation
was synchronized through [PR #2](https://github.com/iam-Seraph/Price-agent/pull/2),
and the separate real-product catalog (Phase 5) was merged through
[PR #3](https://github.com/iam-Seraph/Price-agent/pull/3). The Phase 5
merge commit is `a7cd7e1f12dd7a6e688bc8ea54f01d985fdcf142`.

This document **preserves the original Phase 0–4 findings and local audit
evidence as history**. Mentions of an unpushed branch, absent scheduler,
missing product catalog or "not modified GitHub" in the early sections
describe the earlier audit environment **at the time**, not today's merged
repository. The original `001_initial.sql` append-only price-history
schema was not changed; Phase 5 added a **separate**
`002_catalog.sql` schema. External retailer behavior, production-scale
catalog ingestion and strict type/property tests remain unverified:
the application is **not production-ready**.

For current installation and usage, read [README.md](README.md),
[PHASE5.md](PHASE5.md), and [backend/README.md](backend/README.md).
For the new release evidence, see the Phase 5 appendix at the bottom.

## Scope and provenance

- Inspected the **available local source snapshot**: repository-root `price_agent.py`, `live_price.py`, `requirements.txt`; `backend/price_engine/*.py`; `backend/migrations/001_initial.sql`; `backend/config/selectors.json`; and both `backend/tests/test_*.py`. Source names/line numbers below are relative to this snapshot.
- The supplied environment had `/mnt/data/price_engine/` and loose root files, **not an existing Git checkout**. A separate local, disconnected snapshot repo was assembled at `/mnt/data/Price-agent-audit`, initialized on `baseline-snapshot` (initial import `ff092d5`) and switched to **`audit/hardening`**. That is **not** a branch of the user's Windows checkout or GitHub remote. `AUDIT.md` was subsequently committed with the baseline, and the Phase 2 fixes were added on this branch.
- Actual implementation differs from the supplied assumptions: Python **3.13.5** observed (backend README says 3.11+); `asyncio` for routing; **synchronous `requests` and `sqlite3`**, not `httpx`/async DB inside the package; SQLite storage; **unittest** tests (pytest can run them). Root ReAct agent remains mock/JSON-backed and is **not wired to the backend**. `MAX_STEPS = 6` in `price_agent.py:25`.
- The user's `.env` and secrets were neither inspected nor copied. Real retailer behavior is **not verified**.

## Phase 0 — executed baseline

| Check | Actual result | Limitations |
|---|---|---|
| `cd backend && python -m unittest discover -s tests -v` | **12 tests passed**, ~0.017 s | Mostly functional/fixture tests, no systematic concurrency or error-injection tests |
| `cd backend && python -m pytest -q tests` | **12 passed, 6 subtests passed**, ~0.14 s | Same tests, different runner |
| `python -m mypy --strict price_engine` | **Not run: `No module named mypy`** | No local mypy config found. Not installed; no dependency added without approval |
| `python price_agent.py` from snapshot | **Not run successfully:** `ModuleNotFoundError: No module named 'openai'` | ReAct mock cases previously reported by user; cannot independently verify them in this environment |
| Backend import and fault probes | **Ran offline** | Listed in reproducible evidence below |

### Baseline throughput / p95 — loopback transport, not live retailers

An external temporary benchmark harness (not added to package or tests) ran `HybridRouter.ingest` through a synthetic adapter using **one shared `httpx.AsyncClient`** (`Limits(max_connections=20, max_keepalive_connections=20)`; explicit 2-second connect/read/write/pool timeouts) against a local `ThreadingHTTPServer` on `127.0.0.1` with **25 ms injected server latency**. **120 items**, caller concurrency **20**, token buckets prefilled to avoid rate throttling, circuit breaker threshold raised to avoid intentional server-fault shutdown, configured router retry count **3**. Counts are per attempted item, unless labeled HTTP attempts. p95 is nearest-rank, per-item end-to-end `ingest` latency. These are single-run environment-dependent observations, **not guarantees**.

| Scenario | HTTP responses injected | Items/s | p95 per item | Elapsed | HTTP attempts | Outcome counts |
|---|---|---:|---:|---:|---:|---|
| Healthy | all 200 | **261.51** | **86.5 ms** | 0.459 s | 120 | 120 VALID_PRICE |
| Mixed | 80% 200, 10% 503, 5% 429, 5% 403; deterministic item IDs | **39.16** | **2016.9 ms** | 3.065 s | 144 | 96 VALID_PRICE, 12 TRANSIENT_ERROR, 6 API_THROTTLED, 6 ACCESS_DENIED |

**Measurement boundary:** This exercises the *real router and retry/bucket logic* plus a **synthetic `httpx` transport adapter**; it does **not** benchmark the production `StructuredHTMLClient`, which uses blocking `requests` and does not expose an injectable HTTP client. The local HTTP server exercises an actual socket pool; `httpx.MockTransport` alone would not. No external network requests occurred. The benchmark harness was temporary and not versioned in this report-only phase. Re-run and version an equivalent harness before claiming a Phase 2 performance comparison.

## Phase 1 — findings (code unchanged)

Severity policy from request: **P0** = wrong money, crash, deadlock, data loss; **P1** = reliability or throughput; **P2** = style. Proposed public API or DB changes below **require approval before implementation**.

| ID | File:line | Severity | Evidence / observed failure | Proposed fix (Phase 2 only, subject to approval) |
|---|---|---|---|---|
| F01 | `price_agent.py:51-57,76-90` | **P0** | Money and percentage thresholds use `float` and rounded thresholds. Offline evaluation of the unmodified AST functions accepted `price=0.95`, `avg_30d=1.05`, `low=0.95`, stock true, rating 4.5, 30 samples as `genuine=True`, although exact cent arithmetic says `95*10 <= 105*9` is **false**. A false-positive deal is possible. | Use integer `Paisa` throughout, preserve 30-day average as sum/count, exact integer comparisons, and tests for boundary conditions; changing public tool arguments requires approval. |
| F02 | `backend/price_engine/router.py:26-35,85-113` | **P0** | `CircuitBreaker.allow()` sets `_probe_active=True` for HALF_OPEN; cancellation before `breaker.success()/failure()` does not reset it. Offline cancellation probe: breaker remained HALF_OPEN, probe active, and `allow()` returned False forever. | Lease the half-open probe with cancellation-safe `try/finally`, test cancellation and recovery (including 1,000 cancellations as applicable). |
| F03 | `backend/price_engine/router.py:91-98`; `backend/price_engine/live_html.py:76-96` | **P0** | Router only catches `AdapterFailure`; `ValueError` from a fake adapter escaped `ingest` during offline probe. HTML adapter raises `PermissionError`, `ValueError`, `requests.HTTPError`/transport errors which router does not classify. Unhandled errors can crash aggregate polling. | At router boundary, map transport/parser/unexpected errors to structured typed outcomes, let `CancelledError` propagate, and isolate sibling tasks. No bare catch. |
| F04 | `backend/price_engine/router.py:120-129`; `backend/price_engine/validation.py:39-42` | **P0** | Offline fake adapter returned a `VALID_PRICE` observation for listing ID `other` while requested listing ID was `wanted`; `ingest()` returned it as accepted. `identity_verified=True` is trusted without checking `obs.listing_id == listing.listing_id`. | Verify observation IDs and source identity at the router boundary; reject/quarantine a mismatch; test cross-listing data. |
| F05 | `backend/price_engine/live_html.py:97-98`; `backend/price_engine/models.py:42-45`; `backend/price_engine/storage.py:33-41` | **P0** | Live HTML `source_record_id` is the **content hash**, not a per-poll event ID. Two separately parsed polls with identical HTML had different `observed_at` but **the same `observation_id`** offline; `INSERT OR IGNORE` drops the second legitimate history event. | Generate an ingestion-cycle ID stable across retries but unique for distinct polls; retain content hash separately. Requires discussing any public signature change. |
| F06 | `backend/price_engine/live_html.py:75-98` | **P1** | `async fetch_price()` directly executes synchronous `requests.get()` (up to 20 s timeout), blocking the event loop; no shared `AsyncClient`, `Limits`, four-way `Timeout`, or async shutdown. | Reuse one injected shared `httpx.AsyncClient` with explicit limits and timeouts; tests using `MockTransport` plus socket-based pool benchmark. New dependency/public constructor change needs approval. |
| F07 | `backend/price_engine/storage.py:8-20,23-44`; `backend/price_engine/demo.py:15-27` | **P1** | Synchronous `sqlite3` reads/writes/migrations in execution path, no async offloading or single-writer queue; can block event loop and contend under concurrency. | Isolate DB operations in a bounded dedicated writer/worker or approved async driver; retain transactions, WAL, idempotency, and ordering. Driver dependency or schema changes need approval. |
| F08 | `backend/price_engine/router.py:59-68` | **P1** | `TokenBucket.acquire` sleeps **while holding the lock**, serializing waiters; monotonic clock and sleeper are not injectable. `async with` releases the lock on cancellation, but requests may queue behind a long lock-held sleep. | Compute reservation under lock; sleep outside; inject monotonic clock/sleeper; deterministic cancellation and throughput tests. |
| F09 | `backend/price_engine/router.py:99-111`; `backend/price_engine/live_html.py:87-96` | **P1** | 429 returns immediately with no per-host cooldown or Retry-After scheduling; 503 with Retry-After raises an unclassified HTTP error in HTML adapter. ACCESS_DENIED increments breaker but may require 5 failures before any backoff. | Typed 429/503 Retry-After handling, explicit per-host cooldown, access-denial report and pause; never retry/circumvent denied access; bounded 5xx retries. |
| F10 | `backend/price_engine/router.py:99-112` | **P1** | `DOM_CHANGED` is treated as success (`breaker.success()`), resetting failures; there is no repeated-schema-failure quarantine. | Count per-adapter DOM/schema mismatches, quarantine after configured repeats, no retry on DOM_CHANGED, test isolation. |
| F11 | `backend/price_engine/router.py:87-130`; `backend/price_engine/models.py:7-16` | **P1** | Results are `Observation | None`, with no explicit tool `{ok,error,retryable,price_paisa,display_price}`; unknown outcomes are not exhaustively matched with `assert_never`. Root tool `price_agent.py:96-184,211-240` uses untyped dicts and ambiguous `price` float. | Define typed error/result wrapper, explicit status mapping with `assert_never`, consistent paisa and formatted ₹ display, no raw exceptions. **Public signature change: approval required.** |
| F12 | `backend/price_engine/storage.py:15-21` | **P1** | `accepted_prices` retrieves the last **30 events**, not data within the last **30 days**. No sum/count or lowest-price window aggregation; a caller could misclassify a deal. | Query timestamp range in UTC; define sample policy and sum/count/low using INTEGER SQL; time-window tests. May require new API/schema; approval first. |
| F13 | `price_agent.py:24-49,96-111,148-160`; `backend/price_engine/demo.py:22-27` | **P1** | ReAct tools use the hard-coded USD `CATALOG` and mock JSON `HISTORY`, while backend persists INR SQLite data; a real live check does not feed tools or a 30-day history. Actual context's “these back the tools” is untrue. | After API approval, integrate validated engine/storage into tools; fail closed on missing source, currency, stock, seller rating, or history; keep MAX_STEPS=6. |
| F14 | `backend/price_engine/models.py:25`; `backend/price_engine/validation.py:49-52`; `price_agent.py:51-90`; `live_price.py:62-70` | **P1** | Money models expose bare `int`, anomaly `statistics.median()` yields float for even sample counts, and both root scripts parse money with float. No `NewType('Paisa', int)` barrier; no type-enforced rupee/paisa distinction. | Introduce `Paisa` NewType and use `Decimal` only at input boundary; replace median float comparisons by exact rational integer math; test money path. **Signature change: approval required.** |
| F15 | `backend/price_engine/router.py:17-47,85-111`; `backend/config/selectors.json:8-16` | **P1** | Breakers/buckets are per injected adapter instance, not keyed by retailer/host; no shared global/per-host ordering or semaphores; multi-process state not coordinated. In-process breaker successes can reset unrelated failures. | Explicit per-host rate/breaker/concurrency management, global-before-host order, shared state strategy, cancellation-safe permits, stress tests with hard timeout. |
| F16 | `backend/README.md:19-23,38`; `backend/price_engine/router.py:115-130` | **P1** | There is **no poll scheduler, per-listing in-flight guard, bounded task queue, jittered scheduling, task drain, or shutdown ownership**. Not a defective existing scheduler; the functionality is absent. | Add these once the scheduler/API design is approved; bounded queue and duplicate-poll tests. |
| F17 | `backend/price_engine/live_html.py:23-73,94-98` | **P1** | BeautifulSoup plus JSON-LD graph walk run synchronously in the coroutine after HTTP; arbitrary JSON-LD depth/size can monopolize event loop (3 MB response cap is checked only after full response is downloaded); first nonmatching Product causes early quarantine even if a later matching Product exists. | Bound parsing resource use, run costly parse off-loop, scan all Product candidates before identity conclusion; fixture tests. |
| F18 | `backend/price_engine/storage.py:32-41`; `backend/migrations/001_initial.sql:23-41` | **P1** | `INSERT OR IGNORE` enforces idempotent keys but does not detect a conflicting payload reusing the same record ID; silently returns False instead of reporting inconsistent retries. | On conflict, compare immutable persisted fields and report mismatch without rewriting history; retain unique keys and append-only constraints. |
| F19 | `backend/price_engine/live_html.py:78-86`; `live_price.py:24-38,109-114` | **P1** | DNS allowlist check and actual `requests` connection resolve separately; DNS rebinding/TOCTOU risk is documented in the code. No live test performed. | Approved transport with DNS binding/public-address enforcement and no redirects, not anti-bot evasion. |
| F20 | `backend/price_engine/storage.py:8-13`; `backend/migrations/001_initial.sql:1-55` | **P1** | `sqlite3.executescript` initializes schema without an explicit migration version/transaction block; partial DDL could remain after migration error. Runtime `persist` *does* use `with connection`. | Versioned, explicitly transactional migrations and rollback tests. **DB schema/migration change: approval required.** |
| F21 | `backend/price_engine/models.py:18-49`; `backend/price_engine/adapters.py:6-24`; `backend/price_engine/live_html.py:26-28`; `backend/price_engine/router.py:7` | **P1** | Strict type check could not run; dynamic JSON `Any` and `**kwargs: object` passed into strongly typed dataclass likely need narrowing. Root tools are largely untyped. Do not assert a mypy error count without running it. | Install/run mypy **after approval**, add strict type annotations and exhaustive checks; no unreasoned ignores or weakened config. |
| F22 | `backend/price_engine/router.py:7`; `backend/price_engine/live_html.py:5`; `backend/price_engine/router.py:70-75` | **P2** | Unused `Callable`, `Awaitable`, and `re` imports; frozen Policy lacks `slots=True` though supported. | Defer as style follow-ups; do not change in Phase 2 under the requested scope. |

## Explicit checklist — inspected checks, including passes and unimplemented items

### A. Concurrency

- **Shared async client / limits / four timeouts:** **F06**; absent in package. Benchmark client was harness-only, not an implementation claim.
- **Event-loop blocking (`requests`, `time.sleep`, DB, heavy parsing):** **F06, F07, F17**. **No issue:** `time.sleep()` is **not** called in the router's async retry path; it uses `await asyncio.sleep()` (`router.py:97,103`).
- **Semaphore and token permits / cancellation / backoff / lock order / injectable clock:** **F02, F08, F15**. **No issue:** token-bucket lock uses `async with`, so cancellation releases its mutex (`router.py:60`); router retry backoff occurs *after* `bucket.acquire()` has returned (`router.py:89-104`). No semaphore/global lock exists to inspect or assert release for; monotonic time (`router.py:56,62`) is not injectable.
- **CancelledError / shutdown:** **F02, F06, F16**. **No issue:** no `except asyncio.CancelledError` suppression and no bare catch in router (`router.py:91-98`); cancellation propagates, albeit with the broken HALF_OPEN cleanup. No owned task manager/client shutdown exists.
- **No overlapping polls / jitter / bounded queue:** **F16**; no scheduler is implemented; therefore cannot claim overlapping-poll prevention.

### B. Error boundaries

- **Transient timeouts, 5xx, resets / bounded jitter retries:** **F03, F09**. **No issue:** explicit `AdapterFailure` and returned `TRANSIENT_ERROR` use bounded `Policy.max_attempts` with jitter (`router.py:89-104`); 5xx/transport exceptions from the real HTML client are *not* normalized into these paths.
- **429 / 503 Retry-After / host cooldown:** **F09**. **No issue:** `API_THROTTLED` does **not** trigger HTML fallback (`router.py:123-124`), verified by `test_engine.py:41-47`.
- **DOM_CHANGED no retry, quarantine, no stale price:** **F10**. **No issue:** returned `DOM_CHANGED` is not retried by `_attempt`, and HTML parsing returns no guessed current price when JSON-LD is absent (`live_html.py:73`); repeated mismatch quarantine is missing.
- **ACCESS_DENIED:** **F09**. **No issue:** HTML HTTP 401/403 and redirects become ACCESS_DENIED (`live_html.py:91-93`) and router returns without HTML fallback after API denial (`router.py:108-110,123-124`). CAPTCHA-specific detection not present; no bypass mechanism added.
- **Unknown exceptions / sibling isolation / enum exhaustiveness / bare except:** **F03, F11**. **No issue:** no `except:` or `except BaseException` found in examined package files. Siblings aren't managed by this package; per-item exceptions can propagate to any future orchestration.
- **Structured tool results, unit display, retries vs agent steps:** **F11, F13**. **No issue:** internal router attempts do not increment the ReAct loop counter, which counts model interactions (`price_agent.py:291-343`), and that loop is capped at six. Consistent `{ok,error,retryable}` result and paisa display are missing.

### C. Money and state

- **Decimal at edge / INR lakh grouping / rounding / Paisa NewType:** **F01, F14**. **No issue in backend edge parse:** `parse_inr_paisa` (`validation.py:13-30`) uses `Decimal`, handles `₹1,49,999.00`, rejects >2 decimal places instead of silently rounding, and returns positive integer paisa. **Not compliant globally:** other root code uses floats, explicit rounding policy isn't encoded, and `Paisa` type is absent.
- **Percentage rules exact, mean sum/count:** **F01, F12, F14**. **No issue:** anomaly price-drop/growth comparisons are integer multiplies (`validation.py:43-48`); the genuine-deal rule is not integer-safe in the ReAct agent.
- **Frozen models, slots, nested mutability:** **F22**. **No issue:** `Observation` and `Listing` are `@dataclass(frozen=True, slots=True)` (`models.py:18`, `adapters.py:6`), all their fields are scalar/immutable, and no mutable list/dict fields are present. `Policy` is frozen, but lacks slots.
- **mypy strict / untyped defs / Any leaks:** **F21**, unverified because mypy is unavailable; cannot claim clean or enumerate remaining errors.

### D. Storage

- **INTEGER money / parameterization:** **No issue:** schema defines `price_paisa INTEGER` with positive-value check (`001_initial.sql:28`); store queries and inserts use `?` parameters (`storage.py:16-20,33-40`).
- **Transactions:** **F20**. **No issue for normal writes:** `PriceStore.persist` wraps its insert in a connection context (`storage.py:32-41`). Migration transaction/versioning not assured.
- **Idempotency / append-only:** **F05, F18**. **No issue for true retries:** unique `(listing_id, source_type, source_record_id)` + insert-ignore (`001_initial.sql:40`, `storage.py:33`) prevents identical duplicate rows; `test_engine.py:56-66` verifies duplicate suppression and update rejection; update/delete triggers (`001_initial.sql:54-55`) protect append-only history. **Issue:** distinct identical-content polls are collapsed, and conflicting duplicate IDs aren't reported.
- **UTC timestamps:** **No issue on examined normal paths:** `Observation.__post_init__` requires timezone-aware times and `.observed_utc` converts to UTC (`models.py:34-49`); store generates `ingested_at` in UTC (`storage.py:31`). Schema string checks alone do not validate real UTC semantics for direct SQL clients.
- **Nonblocking DB:** **F07**, not satisfied; SQLite calls are synchronous.

## Offline evidence details (not committed as tests yet)

1. **F01 (false deal):** Executed isolated, unchanged AST-extracted `money` and `evaluate_deal` functions because root's `openai` dependency was missing. Given `price=0.95`, `avg_30d=1.05`, `lowest_30d=0.95`, `budget=1.00`, `in_stock=True`, `seller_rating=4.5`, `sample_count=30`, `genuine=True`. Exact cents rule is false (`950 <= 945` is false). **No repository code was edited.**
2. **F02 (cancelled half-open):** Constructed `CircuitBreaker(threshold=1,recovery_seconds=0)`, opened it, started `router.ingest` with an adapter blocked on `await asyncio.sleep(100)`, cancelled the task. Result: `state='HALF_OPEN'`, `_probe_active=True`, next `allow()` False. This demonstrates a persistent probe slot leak, **not** a general claim of deadlock freedom.
3. **F03 (raw exception):** Fake adapter `fetch_price` raised `ValueError('invalid response')`; unhandled `ValueError` escaped `HybridRouter.ingest`.
4. **F04 (cross-listing):** Requested listing ID `wanted`, fake adapter returned `Observation(listing_id='other', status=VALID_PRICE, identity_verified=True, price_paisa=12, availability=IN_STOCK)`; result was `VALID_PRICE` for `other`, not quarantined.
5. **F05 (lost observations):** Parsed the same local fixture twice, passing the content SHA-256 as record ID as live adapter does. The observations had distinct `observed_at` values but identical `observation_id`; the insert-ignore path would collapse them into one history row.

## Historical approval gate / handoff (at the end of Phase 1 only)

- **Fixed:** Nothing; this is Phase 0–1 only. **Fix commit hashes:** none. The local snapshot import hash `ff092d5` is **not** a fix commit or a commit in the original repository.
- **Verified:** 12 backend unittest tests, 12 pytest results, the synthetic loopback baseline, and five targeted offline diagnostic outcomes detailed above.
- **Not verified:** actual user's checkout branch state; mypy strict; root ReAct test suite (missing `openai`); real retailer responses or policies; production HTTP connection pooling; production p95; scheduler/task drain (not implemented); 1,000-cancellation permit stress; comprehensive sibling isolation or deadlock freedom; 30-day aggregate correctness.
- **Dependencies / public interface / schema requiring permission:** `httpx` in actual project, any async DB driver, `Paisa` and structured tool-result signatures, 30-day-history API, migration format/schema. No such changes made.
- **P2 follow-ups (not for Phase 2):** F22 only; any other low-priority cleanup discovered during fixes should be documented, not bundled into behavior changes.
- **Next action (requires explicit user approval):** Begin Phase 2 on **the user's actual checkout** if available, with one finding and its regression test per commit, prioritized F01–F05 (P0) then P1. Record new measurements against this baseline, without weakening checks or bypassing access restrictions. **Stop here.**


---

## Phase 2 + Phase 4 — implementation and verification results

The historical Phase 1 sections above describe the original defects. This
section records the later implementation; the original table was **not**
rewritten to pretend those defects were absent from the baseline.

### Fixes made — one issue, one regression-bearing commit

| Finding | Fix commit | Verification coverage |
|---|---|---|
| F01 | `0c40875` | Rounding false-positive boundary on legacy USD mock agent (integer minor units for decision threshold) |
| F02 | `ad07b6b` | 1,000 cancelled half-open probes release ownership |
| F03 | `e820e13` | Permission, parser, timeout and unexpected exception classifications plus healthy sibling |
| F04 | `2647f86` | Cross-listing price and unverified stock are quarantined |
| F05 | `ed3eaa0` | Two same-content polls persist as distinct observations; exact retry deduplicates |
| F06 | `30dd77b` | Shared injected async httpx client, bounded streaming, MockTransport tests |
| F07 | `1ab8eb7` | Async SQLite offload with 1,000 cancelled waiters and idempotent writes |
| F08 | `1ca0176` | Injectable monotonic clock, mutex released before backoff/sleep; 1,000 cancellations |
| F09 | `4d36dc2` | 429/503 Retry-After, access denial, host cooldown, no bypass |
| F10 | `8c46afc` | Repeated DOM changes quarantine just the affected host/adapter |
| F11 | `c72902e` | Exhaustive typed `{ok,error,retryable}` result with price_paisa and ₹ display |
| F12 | `3661393` | UTC 30-day exact sum/count/low and integer deal thresholds |
| F14 | `933ed50` | Paisa NewType, exact median comparisons, parser/formatter round-trips |
| F15 | `00c065c` | Global-then-host semaphores with 1,000 cancelled requests releasing slots |
| F16 | `3f83b01` | Opt-in bounded queue and jittered, non-overlapping scheduler; shutdown tests |
| F17 | `edab837` | Bounded HTML/JSON-LD work, multiple-product identity selection |
| F18 | `dd3c593` | Duplicate ID with inconsistent payload is rejected and history preserved |
| F20 | `da82f15` | Explicit transactional migration startup; partial DDL rolls back |

**Phase 4:** commit `ee069e9` adds `dashboard.py`, local Jinja2 template,
static CSS/JavaScript, optional dashboard dependency file, and read-only API
tests. Commit `c3ded26` adds the reproducible offline loopback benchmark and
narrows parser/dashboard type boundaries. The dashboard reads existing
`retailer_listings`, `products`, `price_history` tables with `mode=ro`
and `query_only=ON`; no write handler, schema alteration or direct retailer
fetch is possible from the UI. The optional scheduler is *not running* until
an application explicitly configures it.

### Tests and performance

- `cd backend && python -m unittest discover -s tests -q`: **34 passed**.
- `cd backend && python -m pytest -q tests`: **34 passed, 6 subtests passed**.
- Fault cases and cancellation tests were executed **offline** with synthetic
  adapters, fixtures, and `httpx.MockTransport` (no real retailer called).
- `python -m benchmarks.loopback`: local HTTP socket pool with 120 items,
  25 ms injected latency, 20 concurrent connections, 20 max in-flight
  permits in the benchmark run. Healthy results from two runs were
  **266.22–271.12 items/s** and **83.8–87.5 ms p95**. Initial baseline
  was **261.51 items/s** and **86.5 ms p95**. The p95 moved both below and
  slightly above the single-run baseline; **the non-regression goal is not
  proven** by these noisy single runs.
- Mixed-fault benchmark runs returned many `DEFERRED` without an HTTP attempt
  due to the new per-host cooldown (up to 100/120 items deferred). Their
  measured p95/throughput are **not apples-to-apples** with the original
  all-attempted mixed-fault baseline (39.16 items/s, 2016.9 ms p95).
- Full root `price_agent.py` LLM workflow was not independently run because
  the OpenAI package was unavailable; its isolated deal threshold test passed.

### Unverified and remaining risks

1. **F21: strict mypy not verified.** `python -m mypy --strict price_engine`
   could not execute (`No module named mypy`); pip installation failed due
   DNS/network unavailability. Hypothesis property testing is also
   unavailable here, so deterministic round-trip tests are **not** being
   misrepresented as Hypothesis results. Dependency pins are in
   `backend/requirements-dev.txt` for reproduction elsewhere. The library
   may still have strict type-check errors; no `# type: ignore` was added.
2. **F13 is still open.** The root ReAct tools use separate USD mock prices
   and JSON history. The dashboard is connected to real **local SQLite
   records**, but it does **not** turn the ReAct mock agent into a verified
   retailer-connected agent. Genuine-deal rules in `PriceWindow` apply to
   INR/paisa backend data only; root mock output still carries float prices
   in legacy USD display fields.
3. **F19 is still open.** Domain/IP preflight does not pin DNS across HTTP
   connection creation. Do not activate untrusted live retailers until a
   policy-approved DNS-pinning/SSRF-safe transport is verified.
4. **F15/F16 partial scope:** per-host circuit/bucket state and scheduler
   queues are **in-process only**, not shared across hosts/processes;
   scheduler is opt-in and not wired to a live authorized adapter. A timeout
   on scheduler draining means true infinite blocking was not proven absent.
5. **F20 partial scope:** initialization is now transactionally rolled back,
   but durable versioned migrations have not been implemented (schema
   preservation was required). `ingestion_attempts` logging and operator
   metrics remain unintegrated.
6. No real retailer HTML/API contract or access authorization was validated;
   no cross-process production load test, auth, or TLS configuration was
   exercised. The dashboard must be bound to loopback only until separately
   secured. The real user's Windows Git checkout and GitHub branch have
   **not** been modified. The branch and commits reside in a disconnected
   snapshot under `/mnt/data/Price-agent-audit`.

**P2 follow-ups:** F22 (unused imports/frozen Policy slots/style), plus any
remaining stylistic cleanup. These were not used to disguise behavior changes.

**Completion status:** Local read-only dashboard and key P0/P1 fixes
implemented and unit-tested; **NOT certified production-ready** because
strict type, DNS-pinning, real retailer and cross-process verification are
incomplete. No push, merge or force-push performed.


---

## Release synchronization preparation — 2026-11-18

The `audit/hardening` release candidate was compared against GitHub
`main` at `a91e92859ce87bd10290f0f7612d31b3d231a353`; the remote's
`README.md` rename is preserved instead of reintroducing
`README_price_agent.md`. Existing `.env.example`, `.gitignore`,
`backend/migrations/001_initial.sql`, and `live_price.py` are unchanged.

Release validation on the reconstructed source snapshot:

- `python -m unittest discover -s tests -q`: **34 tests passed**.
- `python -m pytest -q tests`: **34 passed; 6 subtests passed**.
- `python -m compileall -q price_engine tests`: **passed**.
- `git diff --check`: **passed**, no whitespace errors.
- Loopback benchmark (single run, 120 items, artificial 25 ms latency):
  **healthy 262.52 items/s, p95 89.7 ms**; mixed scenario
  **53.60 items/s, p95 49.6 ms, 100 deferred**. This is not a
  demonstrated performance non-regression; healthy p95 is slightly worse
  than the initial single-run 86.5 ms reference.
- No genuine retailer integration tested, and strict mypy / Hypothesis still
  **not run** in this environment; no production-readiness claim.
- Existing migrations and history triggers are unchanged; dashboard routes
  use read-only SQLite access.

The update is scoped to the backend code, offline tests, benchmarking,
requirements and documentation. No secrets or `.env` files are part of the
release candidate. The release is to be published on `audit/hardening` only;
`main` is not to be changed. The historical commit hashes above refer to a
**disconnected local snapshot** and must not be mistaken for the new GitHub
branch commit IDs.

---

## GitHub publication and merged release — 2026-11-18

This section supersedes **only the publication status** in the historical
sections above. The underlying findings, baseline results, original local
commit hashes, unresolved P0/P1/P2 notes, and test limitations remain preserved.

| Milestone | Verified GitHub state |
|---|---|
| Initial reviewed `main` | `a91e92859ce87bd10290f0f7612d31b3d231a353` |
| Published hardening branch | `audit/hardening` at `4e7de97dc2fa02baede315b7cd4c583b66ef1ba7` |
| Pull request | [#1 — Merge hardening and Phase 4 dashboard](https://github.com/iam-Seraph/Price-agent/pull/1) |
| Merged `main` | `89f6b0fa343502797ba697252afb021497ac0b66` |
| Git comparison | Five feature commits and 28 changed files; no force-push |
| Post-merge comparison | `main` has the merge commit and no file differences from the hardening branch |

### Actual published commit IDs (not historical audit-local IDs)

| GitHub commit | Conventional message |
|---|---|
| `d5015840daaa74ea292604d101e6da3a3bfa53e5` | `fix(storage): preserve append-only history and cancellation-safe SQLite access` |
| `48e99756125d8dfe7a14b3109af464f0b95a95aa` | `fix(ingestion): classify failures and enforce exact money and concurrency rules` |
| `4b57c0b85e16350b78e85595da0b82074c4f3d26` | `feat(scheduler): add bounded polling and localhost benchmark` |
| `f17e43caf1b362f77dc2757114b3832a4686ef01` | `feat(dashboard): add read-only SQLite API and responsive price history UI` |
| `4e7de97dc2fa02baede315b7cd4c583b66ef1ba7` | `docs(audit): publish hardening evidence and dashboard runbook` |

The earlier Phase 2 table maps findings to **disconnected local audit commits**,
not these GitHub SHA values. The GitHub commits group the reviewed changes by
storage, ingestion, scheduler, dashboard, and documentation. No claim is made
that each local finding has a one-to-one public commit.

### Consolidated verification and open requirements

- **Previously executed offline tests:** 34 unittest tests and 34 pytest tests
  passed in the reconstructed hardening checkout; compilation and whitespace
  checks also passed. These tests were **not rerun during GitHub PR merge**.
- **Not verified:** `mypy --strict` and Hypothesis properties, real retailer
  integrations and terms/access authorization, DNS-pinned SSRF protection,
  cross-process coordination, and sustained non-regression load testing.
- **Unchanged DB contract:** `backend/migrations/001_initial.sql` and its
  append-only price-history update/delete triggers were left untouched.
- **Dashboard contract:** The FastAPI/Jinja2 app reads an existing SQLite DB
  with read-only connections. It has no authenticated public endpoint,
  automatic retailer polling configuration, or manual ingestion action.
- **Agent separation:** Root `price_agent.py` still uses mock USD price
  history; the backend's genuine-deal criteria use integer INR paisa.
- **Security:** The published diff did not contain `.env` or credential files;
  this is not equivalent to an exhaustive scan of all Git history.
- **Outstanding:** Original findings F13 (root tools not integrated),
  F19 (DNS pinning), F21 (strict typing verification), cross-process rate
  coordination, attempt logging and versioned migrations remain open.

**Documentation structure:** The [root README](README.md) is now the unified
quick-start and current project summary; [backend/README.md](backend/README.md)
is the implementation/runbook detail; this `AUDIT.md` retains the complete
historical finding matrix, test evidence, published commit history, and
remaining security/reliability limitations.


---

## Phase 5 — real-product catalog publication and current evidence (2026-11-18)

**Scope:** This release adds an **independent** real food/grocery product
identity catalog from Open Food Facts, not a general electronics dataset,
real retailer quotes or price histories. The original ReAct USD mock agent
remains separate. The Phase 5 importer requires a user-downloaded
Open Food Facts bulk file; no million-product SQLite database was committed
or automatically populated.

| Milestone | GitHub / evidence |
| --- | --- |
| Previous `main` before Phase 5 | `5deaee07080b3e2f201a112f7a73f832d154af87` (PR #2 documentation merge) |
| Feature branch | `feat/phase5-real-product-catalog` |
| Merged pull request | [PR #3](https://github.com/iam-Seraph/Price-agent/pull/3), merged 18 November 2026 |
| Merge commit | `a7cd7e1f12dd7a6e688bc8ea54f01d985fdcf142` |
| Passed CI | [GitHub Actions run 44166599779](https://github.com/iam-Seraph/Price-agent/actions/runs/44166599779): **37 backend unittest tests**, Python 3.11, compilation |
| Data-source and license | Open Food Facts official export; database under ODbL obligations |
| Bulk import count | **Not independently run or verified**; 1,000,000 accepted source rows is the default configured target, not measured unique catalog contents |

### New implementation contracts

- **Independent schema:** `backend/migrations/002_catalog.sql` adds
  `product_catalog`, `catalog_import_runs`, an FTS5 index and index
  synchronization triggers. The existing Phase 1 schema and price-history
  triggers in `001_initial.sql` were preserved.
- **Importer:** `backend/price_engine/catalog_import.py` streams a local
  CSV/TSV/gzip export, validates barcodes and names, applies best-effort
  restricted-category filtering, and upserts bounded batches with an
  actual database row count. The import does **not** verify prices, scrape
  retailers, or automatically download source records.
- **Read-only API and UI:** `GET /catalog`, `GET /api/catalog/stats`,
  `GET /api/catalog/search`; server-side indexed query, pagination,
  explicit source links and attribution. The dashboard remains local,
  read-only and unauthenticated.
- **Tests:** `backend/tests/test_catalog.py` adds fixture-based gzip/CSV
  import, idempotent duplicate/upsert, FTS search, pagination and
  separation-from-price-history cases. The successful 37-test CI
  result includes the pre-existing backend suite.
- **Demo limitation:** `price_engine.demo` may raise
  `ValueError: Conflicting duplicate observation ID or source record`
  when rerun against a populated DB. The demo uses the same fixture
  source ID with a fresh timestamp. This is not evidence of failed
  catalog ingestion or a missing SQLite dependency. Preserve the
  existing database or use a new filename.

### Explicitly unverified / next gates

1. **One million unique real items** have **not** been shown imported.
   The CLI cap counts accepted source rows; duplicates and filtering
   reduce the resulting unique table size. Bulk download, storage
   footprint, indexing throughput and query latency require real-world
   measurement.
2. **No verified retailer prices or availability** are present in the
   Open Food Facts catalog. It must not drive price-alert decisions
   without a separate trusted retailer-source and validation contract.
3. **Root AI tools remain disconnected** from this catalog and the
   backend's verified INR-paisa history. Existing F13 remains open.
4. The prior open production/security requirements remain: DNS pinning
   (F19), strict mypy/Hypothesis checks (F21), authorized retailer
   contracts, process-shared rate/circuit coordination, durable schema
   migrations, observability, public auth/TLS and production load tests.
5. ODbL attribution/share-alike obligations must be reviewed for any
   redistributed derived database. Source data quality and category
   classification need independent validation.

The updated root [README.md](README.md) is the current quick start;
[PHASE5.md](PHASE5.md) documents importing and checking real counts.
This appendix **adds** release evidence and does not rewrite the
historical Phase 0–4 matrix or its originally observed results.
