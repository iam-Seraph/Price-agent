# Offline release validation

This repository's source-attributed offer pipeline, deterministic shopping analysis, opt-in monitoring, alert queue, audit and local UI can be tested **without real provider accounts or retailer traffic**.

## Run the whole offline check set

From the repository root, with Python 3.11+ and Node.js 22+:

~~~bash
python -m pip install -r backend/requirements-workspace.txt -r backend/requirements-dev.txt
python scripts/full_check.py
~~~

The script runs **all** of these, even if one fails: Markdown link validation; `pytest` and `unittest` discovery for `backend/tests/`; compilation of the root Python launchers, backend and scripts; JS syntax checks for Intelligence Studio, verified UI and static website; and the Node.js Web Worker test suite. It prints a per-step result and exits nonzero if any step fails. The same command runs in GitHub's Workspace regression workflow.

## End-to-end smoke path

`backend/tests/test_e2e_verified_flow.py` uses a temporary SQLite file and **invented test fixtures only**. It covers creating an explicit watch, enabling an alert rule, persisting mock provider-shaped historical observations, processing one mocked provider search, qualifying/enqueuing a deterministic alert, read-only product research, observed history, integrity audit, HTTP API responses and **mocked** delivery. The test never sends email or requests a retailer.

## Correctness and security fixes

- The opt-in `price_watch.py ... run --continuous` path now passes its `AlertStore` on **every** iteration, like one-shot mode. Alert delivery still requires explicit channel consent and a separate dispatcher.
- `price_audit.py` opens **existing** SQLite databases read-only. Running against a nonexistent path returns an error without creating a parent directory or new DB.
- `real_price_agent.py` defaults to the shared `tracker.sqlite3` file used by watch, research, assistant and audit CLI tools. Explicit `--db` arguments remain supported for existing installations.

## What these checks cannot establish

- Credentials and provider network access were not provided to the CI runner, so no live SerpApi/Groq/SMTP/Telegram requests are tested.
- Mocked source prices are not independently confirmed retailer prices.
- Standalone simulated/virtual product datasets are not production inventory.
- Strict mypy and Hypothesis, retailer contract tests, large Open Food Facts imports, real browser hardware, multi-user security and external production deployment remain separate work. Never treat a passing offline suite as a production certification.
