# Phase 5 — Loops 41–50: source-qualified alerts and opt-in delivery

This is the **new** alert Phase 5 checkpoint, distinct from the existing PHASE5.md catalog-import documentation. It builds upon merged Phases 1–4 and retains existing dashboard, API, agent and monitor commands.

--- LOOP [41]: Durable alert schema ---
Created subscriber channel rules and uniquely keyed delivery outbox records in SQLite. No contact details or API secrets are stored.

--- LOOP [42]: Explicit subscription management ---
Added create/disable channels per watch, with disabling also cancelling queued deliveries.

--- LOOP [43]: Deterministic alert enqueueing ---
Only an ALERT from source-backed history that meets all existing evidence criteria can enqueue an alert. One queue event per watch/offer/channel/day, with pending-queue and 24-hour delivery cooldown checks.

--- LOOP [44]: Delivery leases ---
Added bounded claims to prevent two workers sending the same pending notification at once.

--- LOOP [45]: Delivery outcomes and retries ---
Persisted delivered/queued/failed status, safe error codes and capped retry counters. Delivery is at-least-once, not exactly-once, after a worker crash.

--- LOOP [46]: Authenticated transports ---
Implemented TLS SMTP email and HTTPS Telegram bot sendMessage with credentials only from environment variables; never in the repository or SQLite.

--- LOOP [47]: Monitoring hook ---
Opted-in watch monitors enqueue qualified alerts based on newly seen real provider prices.

--- LOOP [48]: Revalidation before dispatch ---
A delivery worker rechecks the latest source evidence and exact budget before sending, suppressing stale or changed deals.

--- LOOP [49]: Operator CLI ---
Created explicit enable/list/disable/dispatch commands; no auto-sending by web page or on module import.

--- LOOP [50]: Offline regression ---
Added mocked tests covering no-consent, deduplication, lease exclusivity, successful delivery, missing credentials, retries and cancellation.

## Operator setup

Start with a saved real-product watch:
```bash
python price_watch.py --db tracker.sqlite3 add "laptop" --budget 60000 --currency INR --interval-minutes 60
python price_watch.py --db tracker.sqlite3 list
```

Copy a real watch ID from `list`. Enable the channel using that exact value:
```bash
python price_alert.py --db tracker.sqlite3 enable WATCH_ID_FROM_LIST --channel TELEGRAM
python price_alert.py --db tracker.sqlite3 list
```

Configure **new, private** credentials as Codespaces secrets or in a local untracked `.env`. For Telegram, use `PRICE_AGENT_TELEGRAM_BOT_TOKEN` and `PRICE_AGENT_TELEGRAM_CHAT_ID`. For SMTP, use `PRICE_AGENT_SMTP_HOST`, `PRICE_AGENT_SMTP_PORT`, `PRICE_AGENT_SMTP_USER`, `PRICE_AGENT_SMTP_PASSWORD`, `PRICE_AGENT_EMAIL_FROM` and `PRICE_AGENT_EMAIL_TO`.

Monitor then dispatch explicitly:
```bash
python price_watch.py --db tracker.sqlite3 run
python price_alert.py --db tracker.sqlite3 outbox
python price_alert.py --db tracker.sqlite3 dispatch
```

No real messages are sent by tests. Actual SMTP/Telegram delivery requires private credentials and a qualified, newly observed price event. The system cannot guarantee the provider has genuine stock or seller-rating evidence. Without enough confirmed inputs it fails closed and does not notify.

## Security boundaries

- Keep the local server loopback-only. No public signup, bulk email campaign or unrestricted contact targeting is implemented.
- Delivery is opt-in, operator-controlled and configured for **one private destination** per channel, not per-user stored contacts.
- The at-least-once queue may duplicate a message after a crash between actual delivery and recording the receipt. No exactly-once delivery claim is made.
