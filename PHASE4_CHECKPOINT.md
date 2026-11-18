# Phase 4 — Loops 31–40: opt-in scheduled price monitoring

This checkpoint builds directly upon Phase 3 and adds **explicit local-only monitoring**. Nothing polls automatically when importing the project or loading the browser dashboard.

--- LOOP [31]: Persistent watch schema ---
Create validated watch rules and append-only monitor run records in additive SQLite tables.

--- LOOP [32]: Watchlist CRUD ---
Implement checked watch creation, listing and disable operations. Persist budget in exact currency minor units; never store API keys.

--- LOOP [33]: Lease-based scheduling ---
Atomically claim due watch rules with short leases so two workers do not poll the same query at once.

--- LOOP [34]: Auditable completion ---
Record every polling outcome and advance due times. Extend cooldown after provider or validation failures.

--- LOOP [35]: Real-source monitor ---
Use the fixed-origin SerpApi adapter and persist only validated provider offer objects to the verified SQLite tables.

--- LOOP [36]: Explicit worker CLI ---
Add an operator-controlled program with one-shot or continuous modes. Workers do not start inside the dashboard.

--- LOOP [37]: Stable root launcher ---
Expose the watch CLI as `price_watch.py` without changing the existing Price Agent commands.

--- LOOP [38]: Read-only watch audit access ---
Add bounded retrieval of the latest watch processing outcomes and metrics.

--- LOOP [39]: Local API visibility ---
Expose watch rule and run history through read-only FastAPI endpoints; keep writes under the CLI until user authentication exists.

--- LOOP [40]: Regression tests ---
Cover validation, lease exclusivity, polling retries, absence of fabricated price observations, and watch read APIs.

## Usage

Install dependencies from the root:
```bash
python -m pip install -r backend/requirements-workspace.txt -r backend/requirements-dev.txt
```

Add a query watch, with a minimum 15-minute interval:
```bash
python price_watch.py --db tracker.sqlite3 add "wireless mouse" --budget 1200 --currency INR --interval-minutes 60
```

Inspect or disable saved rules:
```bash
python price_watch.py --db tracker.sqlite3 list
```
Disable one real watch ID using `python price_watch.py --db tracker.sqlite3 disable` followed by the watch ID from the previous command.

Poll only when explicitly started, with a private `SERPAPI_KEY` configured:
```bash
python price_watch.py --db tracker.sqlite3 run
```

Continuous local monitoring is opt-in:
```bash
python price_watch.py --db tracker.sqlite3 run --continuous --sleep-seconds 60
```

The process must stay running for continuous monitoring. Codespaces and laptops are not 24/7 hosting by default; there is no hosted monitoring service or cloud database at this checkpoint.

### Boundaries

- The provider returns attributed quotes, not independently audited retailer prices.
- A 429/403 cannot be bypassed by the monitor. Underlying bounded retries only cover transient transport/5xx issues.
- A watch rule currently records fresh observations, but does not yet send email, Telegram or background push notifications.
- Only local `/api/verified/watches` and `/api/verified/watch-runs` read endpoints are exposed; the unauthenticated server must stay loopback-only.
