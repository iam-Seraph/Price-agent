# Phase 7 checkpoint — Loops 61–70: source-grounded shopping research

Builds on the merged source-attributed ingestion and opt-in local dashboard.

--- LOOP [61]: Safe SQLite product lookup ---
Add parameterized, bounded, literal-keyword searches of stored provider offers. Explicitly escape SQL LIKE wildcard characters.

--- LOOP [62]: Budget-aware research ---
Evaluate real observed prices, known stock status, freshness and budget for every independent retailer listing.

--- LOOP [63]: Cross-store comparisons without false SKU matching ---
Sort distinct source offers side by side and state that similarly named variants may differ in storage size, warranty, condition or specs.

--- LOOP [64]: Historical price context ---
Attach deterministic 30-day deal decisions and price-history sample counts from SQLite. AI never invents historical prices.

--- LOOP [65]: Evidence explanations ---
Classify a listing as historical evidence-backed, budget-only candidate, or insufficient evidence. Missing seller ratings and short history remain visible cautions.

--- LOOP [66]: Read-only research command ---
Add `price_research.py` for local, offline research without requiring API credentials.

--- LOOP [67]: Research REST interface ---
Expose `GET /api/verified/research` to compare previously stored offers. It never contacts retailers or providers.

--- LOOP [68]: Browser comparison panel ---
Add a separate saved-offer comparison form to the verified dashboard.

--- LOOP [69]: Safe frontend rendering ---
Render sourced comparison results with DOM text nodes, not interpolated HTML.

--- LOOP [70]: Security and accuracy tests ---
Test strict currency separation, budget candidates, mismatched product assumptions, literal search wildcards, injection strings and HTTP limits.

## Commands

Install:
```bash
python -m pip install -r backend/requirements-workspace.txt -r backend/requirements-dev.txt
```

Research stored offers from the repository root without network access:
```bash
python price_research.py "headphones" --budget 3000 --currency INR --db tracker.sqlite3
```

Visit the existing local `/verified` dashboard for saved-offer comparisons.

**Scope boundary:** Product research is limited to previously observed individual retailer offers. The app cannot establish that separately identified product models have equal specs or warranties. It does not predict future prices, purchase items, or confirm retailer stock independently. An unobserved catalog result is never silently substituted for a real price.
