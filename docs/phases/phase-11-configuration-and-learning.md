# Phase 11 — API configuration and controlled local learning

**Scope:** This extension provides a secret-safe API configuration view and an explicitly enabled, reversible **preference memory**. It does **not** train or fine-tune a language model, crawl Google Search, or install unlimited website connectors.

## API keys and configuration

Copy the tracked [example configuration](../../.env.example) to a local file named `.env` at the root. The local workspace server and existing CLIs read that file without overriding actual environment variables. Set only the optional integrations you use:

- `SERPAPI_KEY` — supported explicit Google Shopping queries. Provider-reported observations, not retailer-verified prices.
- `GROQ_API_KEY` and `GROQ_MODEL` — optional AI explanations; models, quota and availability change.
- `OPENAI_API_KEY` — optional legacy provider, not required by verified research.
- `PRICE_AGENT_TELEGRAM_BOT_TOKEN`, `PRICE_AGENT_TELEGRAM_CHAT_ID` — optional opt-in Telegram notifications.
- `PRICE_AGENT_SMTP_HOST`, `PRICE_AGENT_SMTP_PORT`, `PRICE_AGENT_SMTP_USER`, `PRICE_AGENT_SMTP_PASSWORD`, `PRICE_AGENT_EMAIL_FROM`, `PRICE_AGENT_EMAIL_TO` — optional SMTP notifications.

Use `python price_config.py` or `GET /api/verified/configuration` for key-presence status. `CONFIGURED_UNVERIFIED` means **only** that a non-placeholder value appears present: no network call, credential validation, free-quota confirmation, or service billing check occurs. Credentials are not printed in output or returned to the browser. Never upload the private `.env`.

## Learning from the operator

From `/verified`, enable **Opt-in local learning**, inspect a source-linked offer, and select **Prefer** or **Avoid**. Alternatively, run:

~~~bash
python price_learning.py --db tracker.sqlite3 status
python price_learning.py --db tracker.sqlite3 enable --confirm
python price_learning.py --db tracker.sqlite3 prefer OFFER_ID
python price_learning.py --db tracker.sqlite3 avoid OFFER_ID
python price_learning.py --db tracker.sqlite3 forget OFFER_ID
python price_learning.py --db tracker.sqlite3 disable --confirm
python price_learning.py --db tracker.sqlite3 clear --confirm
~~~

`OFFER_ID` must match a saved 64-character offer ID from `python real_price_agent.py --list`. No raw chats, user identifiers, personal notes, browser history, arbitrary website content or API keys are persisted as feedback. Data is stored locally in `verified_offer_feedback` and capped at 500 active offer votes. Opting out pauses use of existing votes; `clear --confirm` **deletes all votes and disables learning** while preserving provider-observation history.

Research returns `research.personalization.ranked_offer_ids` **only if enabled**. Ordering puts eligible, current, under-budget source-attributed listings first; within that eligibility group an explicitly preferred offer appears before an unvoted one, and an avoided offer appears after. Price remains a tie-breaker. The `comparison.rows` output continues to rank objectively by budget eligibility and price, and deterministic `ALERT` checks remain unchanged. The app labels the personalized result order as user preference rather than a certified recommendation.

## Learning from Google and other sources

The *source learning* mechanism is the existing **append-only, provenance-tagged observation history**, which feeds trend, anomaly and comparison code. The supported Google Shopping access is via **SerpApi**, not direct Google website scraping. The independent **Open Food Facts** importer may add properly attributed grocery identities but **never retailer price claims**. Untrusted product titles, descriptions and URLs are treated only as data; they may not trigger tools, write preferences or override deterministic rules. New retailer integrations require separate authorization, connector contracts, rate-limit handling and source-specific offline tests.

## Local HTTP endpoints

- `GET /api/verified/learning` — enabled flag and number of saved votes.
- `POST /api/verified/learning/opt-in` — `{"enabled":true,"confirmed":true}` to enable; false pauses.
- `POST /api/verified/learning/feedback` — `{"offer_id":"...","preference":"PREFER"}` or `"AVOID"`.
- `POST /api/verified/learning/forget` — `{"offer_id":"..."}`.
- `POST /api/verified/learning/clear` — `{"confirmed":true}` permanently deletes all feedback and pauses learning.
- `GET /api/verified/configuration` — offline configuration readiness only.
- `GET /api/verified/research?q=keyboard&budget=3000` — existing source research with separate opt-in preference ordering.

All writes need a same-origin browser request, but this is **not an authentication solution**. The server remains local-only, single-operator; do not expose it to the public internet.

## Verification

`python scripts/full_check.py` covers backend pytest and unittest, JS and Python compilation, Node worker tests, and documentation links. New `backend/tests/test_phase11_learning.py` uses entirely invented source-shaped quotes and does not access Google, Groq, email, Telegram, shopping sites or real keys. Passing offline tests does not prove live integration works.
