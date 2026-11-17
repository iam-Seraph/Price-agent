# Price-Checker & Deal Tracker Agent — Learning Project

## Files
- `price_agent.py` — main Python application; includes mock catalog, tools, ReAct loop and offline tests.
- `requirements.txt` — Python packages.
- `price_history.json` — example history data for learning. **The current script creates its own temporary copy at runtime**; this file is a reference fixture, not required for execution.

## Setup (Python 3.10+)
```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run offline tests (no API key)
```bash
python price_agent.py
```
Expected: 6 PASS cases: A, B, C1, C2, D, E.

## Run with the model
Copy `.env.example` to `.env` **on your own computer**, then replace the placeholder key with your real key. `python-dotenv` loads `.env` automatically when the script starts. **Never upload `.env` to Drive or GitHub.** Alternatively, set `OPENAI_API_KEY` in your shell. The example model ID is `gpt-6-luna` as specified for this project; if unavailable on your account, set `OPENAI_MODEL` to a supported compatible model.

macOS/Linux:
```bash
export OPENAI_API_KEY="YOUR_KEY"
python price_agent.py --product headphones-a --budget 280
```
Windows PowerShell:
```powershell
$env:OPENAI_API_KEY="YOUR_KEY"
python price_agent.py --product headphones-a --budget 280
```

## Learn in order
1. Python functions, dictionaries, dataclasses, sets, exceptions and `pathlib`.
2. JSON reading/writing, schemas and argument validation.
3. Price math, averages, minimums, thresholds and deterministic tests.
4. HTTP requests, HTML parsing and source trust.
5. OpenAI function tools and assistant/tool message protocol.
6. ReAct loop, state, guardrails, error recovery and alert idempotency.
7. SQLite, scheduled tracking and webhooks.

## Important notes
- The code defaults to `USE_LIVE_SCRAPING = False`; all sample products and prices are fictional.
- The six offline tests were checked with an SDK import shim, not a real OpenAI API request.
- Live URL fetching is not production hardened (robots/ToS, SSRF, currency, data freshness and source reliability need work).
- `price_history.json` is supplied for inspection; the script writes its own fixture in a temporary directory.
- Do not upload `.env`, credentials or API keys to Google Drive.

## Safe GitHub upload
1. Download the source files, `.env.example`, and `.gitignore` into the same project directory.
2. Copy `.env.example` to `.env` **locally** and put your real API key only in `.env`.
3. Verify `.gitignore` is present **before** running `git add`.
4. Run `git init`, `git add .`, then `git status --short`. Confirm `.env` is NOT listed.
5. Commit and push only after checking the staged files. Never paste a key into screenshots, README, issues, logs, or code.
6. If a key is ever committed or shared, revoke/rotate it immediately in the API dashboard; deleting the file from a later commit is not enough.

The `.env.example` file is safe to publish because it contains a placeholder, not a credential. `.gitignore` does not protect a secret that was already tracked; use `git rm --cached .env` if needed and rotate any exposed key.

## Groq API configuration
Copy `.env.example` to `.env`, set `GROQ_API_KEY` locally, and leave `AI_PROVIDER=groq`. Install dependencies using `pip install -r requirements.txt`. Run offline checks with `python price_agent.py`, then invoke the model using `python price_agent.py --product headphones-a --budget 280`. This uses Groq's OpenAI-compatible endpoint. The script uses simulated catalog data by default; it is not a real retailer price monitor. Never commit `.env`. `git status --short` should not show it. The live Groq API call requires your own key and may incur charges.

## NEW: Live product price checker with Rich terminal display

The `live_price.py` command retrieves **current publicly exposed page data** from an HTTPS product URL and prints a styled table. It supports common structured Product JSON-LD and product price meta tags. It is separate from the Groq-powered mock-data ReAct agent; the two modes are not yet integrated.

```bash
pip install -r requirements.txt
python live_price.py --url "https://www.amazon.in/YOUR-PRODUCT-PAGE" --budget 3000 --currency INR
```

Supported retailer domains currently include amazon.in, amazon.com, flipkart.com, croma.com, reliancedigital.in, myntra.com, bestbuy.com, and walmart.com. These are *permitted input domains*, not guaranteed working integrations: stores may require JavaScript, block bots, redirect, or omit structured price data. Follow each retailer's terms and access restrictions. No CAPTCHA bypass is implemented. The tool never guesses a missing price, stock, seller rating, or history. **Within budget is not proof of a genuine discount.** Currency mismatches are not compared. The tool does not track prices over time yet.

This command uses live HTTP requests; `python price_agent.py` continues to run the original mock-data AI workflow.
