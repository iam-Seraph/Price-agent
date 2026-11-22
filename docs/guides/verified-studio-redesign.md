# Verified dashboard — Studio-inspired redesign

The live, source-attributed Price Agent dashboard at /verified now shares the visual language of the fictional /intelligence Studio without mixing the two datasets.

## Visual and interaction changes

- Studio-inspired dark sidebar, navigation, breadcrumb topbar, purple gradient search hero, metric cards, graphical offer cards and a focused evidence inspector.
- Dedicated sections for saved comparisons, opt-in watches, deterministic shopping commands and personal preferences.
- Responsive desktop, tablet and mobile layouts, labeled native inputs, a skip link, clear focus indicators and live status messages.
- Search chips and assistant examples populate fields only. No provider request or mutation occurs without explicit user action.
- Cards contain provider-reported price, merchant, recorded timestamp and stock state. Their abstract decorative lettermarks are not invented product photography.
- Inspecting a card selects the real saved offer and opens the existing history / analysis section. External source links require HTTPS, are shown as external links, and use noopener noreferrer.

## Unchanged real-data safeguards

All established JS control IDs and verified API calls remain available: explicit SerpApi search, SQLite provider observations, historical and anomaly checks, read-only research, watches and alert consent, command preview/execute, opt-in local preferences, and presence-only API configuration reporting.

The dashboard never inserts demo offers into verified storage, never fills empty states with fictional prices, never starts background watches on page load, and never treats provider-reported price as independently verified. It does not show API keys. The separate Intelligence Studio remains fictional.

The redesign uses no external fonts or CDNs, and works under the existing strict local Content Security Policy.

## Run

From repository root:

~~~powershell
python -m backend.price_engine.workspace --db tracker.sqlite3 --workspace-db workspace.sqlite3 --host 127.0.0.1 --port 8000
~~~

Open http://127.0.0.1:8000/verified and refresh with Ctrl + Shift + R after pulling the changed files.

## Verify

~~~bash
python scripts/full_check.py
~~~

A dashboard regression also validates each DOM ID used by the JavaScript against the new template.
