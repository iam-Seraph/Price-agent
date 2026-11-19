# Phase 8 checkpoint — Loops 71–80: bounded natural-language shopping commands

This phase builds on source-attributed SQLite research and deliberately uses a deterministic command grammar instead of open-ended LLM-generated actions.

--- LOOP [71]: Explicit command grammar ---
Support “watch X below ₹N”, “notify me when X drops below ₹N”, and “compare X under ₹N” with INR and USD currencies. Unknown requests fail closed.

--- LOOP [72]: Safe action planner ---
Read-only comparisons may run against stored data. Saving a watch always requires confirmation, and never automatically starts polling or alert delivery.

--- LOOP [73]: Operator CLI ---
Add `price_assistant.py` which previews command intent by default and requires `--confirm` to create a watch.

--- LOOP [74]: Idempotent saved watches ---
Atomically reuse an existing matching enabled watch instead of creating duplicate watch rules on repeated requests.

--- LOOP [75]: Local plan API ---
Add `POST /api/verified/assistant/plan` which interprets a command without side effects.

--- LOOP [76]: Confirmed execution API ---
Add origin-protected `POST /api/verified/assistant/execute`; written watch state requires `confirmed: true`.

--- LOOP [77]: User-visible command preview ---
Add a separate plan-first panel to the real provider dashboard. Unsupported requests show a validation message.

--- LOOP [78]: Explicit approval interaction ---
Show a user confirmation step for watch creation and clear pending approval if the source command changes.

--- LOOP [79]: Offline regression and UI polish ---
Test the grammar, currency parsing, no-write preview, idempotency, read-only comparisons and HTTP approval constraints.

--- LOOP [80]: Checkpoint validation ---
Document runnable commands, permissions and roadmap readiness; verify all existing and new regression suites before merge.

## CLI examples

```bash
python price_assistant.py "compare headphones under ₹3000" --db tracker.sqlite3
python price_assistant.py "watch headphones below ₹3000" --db tracker.sqlite3
```

The second command shows a preview, **not a watch write**. To explicitly save a rule, append `--confirm`.

The browser interface is under `http://127.0.0.1:8000/verified` when the local workspace server is running. Only the local API executes confirmed watch saves. No bank details, payments, cart purchases, arbitrary file access or shell instructions are supported.

## Security / accuracy

- Commands are deterministic patterns, not general artificial intelligence. No unknown instruction is interpreted optimistically.
- Only previously stored provider observations are used for comparisons. The application does not claim same-SKU equivalence or real-time merchant verification.
- Natural-language “notify me” saves a watch but does not promise notification. SMTP/Telegram channels, private credentials, a running monitor and delivery process are separately required.
- This is a loopback-only development service; production deployment needs authentication, stronger CSRF defenses, deployment configuration and rate limiting.
