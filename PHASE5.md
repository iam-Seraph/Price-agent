# Phase 5 — real product catalog (target: 1,000,000)

**Release status:** Phase 5 was merged to `main` on **18 November 2026**
through [PR #3](https://github.com/iam-Seraph/Price-agent/pull/3),
merge `a7cd7e1f12dd7a6e688bc8ea54f01d985fdcf142`.

This phase adds a separate SQLite product-identity catalog. The importer
can process **up to one million accepted source rows per invocation** by default
from an official Open Food Facts bulk export. The **actual number of unique
products may be lower** because of duplicates and exclusions. No dataset is
committed to GitHub, downloaded automatically or verified imported at
the million-row scale. Imported counts are reported by the CLI and stats API.
No generated products or prices are shipped.

## Source, license and scope

**Coverage:** Open Food Facts primarily contains food and grocery products.
It is **not** a million-item electronics/phone catalog. Other product
categories require a separate lawful, appropriately licensed data source.

- Source: https://world.openfoodfacts.org/data
- Bulk export: https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz
- Format: UTF-8 tab-separated fields (despite the .csv extension), gzip.
- License: Open Database License (ODbL 1.0) for the database and Database
  Contents License for its contents. Give attribution to Open Food Facts
  contributors, link to the license, and comply with ODbL share-alike and
  redistribution requirements for derived databases.
- Images have a separate license and are NOT included in this feature.
- Imported: source/barcode, name, brand, category, quantity, countries,
  source URL, source update timestamp and import provenance.
- Excluded: prices, availability, seller ratings, generated observations,
  scraped offers, and active polling.

Open Food Facts data is community-maintained and may be incomplete or wrong.
The provider explicitly recommends bulk download rather than issuing hundreds
of thousands of API requests. This pipeline makes no network requests.

## Windows / VS Code PowerShell

Start from the repository root on the merged **`main` branch**. First run
`git switch main` and `git pull --ff-only origin main` if your local
checkout has not been updated.

~~~powershell
python -m pip install -r backend/requirements-dashboard.txt
New-Item -ItemType Directory -Force backend/data | Out-Null
curl.exe -L --fail --retry 3 "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz" -o "backend/data/openfoodfacts.csv.gz"
cd backend
python -m price_engine.catalog_import --input data/openfoodfacts.csv.gz --db demo_fresh.sqlite3 --max-rows 1000000
python -m price_engine.dashboard --db demo_fresh.sqlite3 --host 127.0.0.1 --port 8000
~~~

Open http://127.0.0.1:8000/catalog. Use the SAME database filename for
the importer and dashboard. For the existing demo, demo_fresh.sqlite3 is
recommended. For a newly named DB, run the existing price_engine.demo once
first to create the original history/listings schema before opening the
dashboard. Do not repeatedly run demo on an already populated database.

The upstream export may require gigabytes of bandwidth/disk. Downloading it
and building a million-row local database is an explicit user action, NOT a
GitHub build step. If the direct download is unavailable, obtain the bulk
export from the official data page and provide its local path.

## Import behavior

- Streams .csv, .tsv, .csv.gz, and .tsv.gz without extracting the entire
  file in memory. Accepts official tab-separated and standard comma CSV.
- Skips records without valid numeric 8–14-digit codes or product names,
  and filters certain age-restricted/intoxicating categories by keywords.
  This is a best-effort keyword filter, **not an exhaustive content audit**.
  Keeps barcodes as text so leading zeros are preserved.
- An import cap of 1,000,000 means accepted input rows, NOT guaranteed
  distinct products. Duplicates lower the resulting unique count.
- Upserts changed data by source + source product ID; unchanged repeats are
  idempotent. Commits in bounded 2,000-row transactions using SQLite WAL.
- The unique total is obtained via a real SQL COUNT query. A completed run
  records scanned/accepted/skipped rows, total products, source and timestamp.
- The FTS5 index covers name, brand and category; no unbounded client fetch.
- The import never modifies the append-only retailer price_history table.

Try a smaller run first:

~~~powershell
python -m price_engine.catalog_import --input data/openfoodfacts.csv.gz --db demo_fresh.sqlite3 --max-rows 10000 --batch-size 1000
~~~

Then repeat with --max-rows 1000000. The existing products will upsert,
not duplicate. Progress is printed in the terminal. The exported file
must contain enough distinct eligible records to reach the target.

## Read-only catalog

| Endpoint | Purpose |
| --- | --- |
| GET /catalog | Search interface, pagination and attribution |
| GET /api/catalog/stats | True row count, source, last completed run |
| GET /api/catalog/search?q=oats&limit=25&offset=0 | Indexed token/prefix search |
| GET /api/listings | Existing retailer listing endpoint, unchanged |

Search is limited to 100 rows per page, uses prepared SQL parameters and
escaped FTS tokens, and does not return a retailer price. Without an import,
the API responds with ready: false and empty results. Dashboard mode is
read-only and still bound to 127.0.0.1.

## Common problems

- **The catalog is empty:** You have not imported an export into the
  database that the dashboard was started with. Verify that both commands
  use the **same** `--db` filename and inspect `/api/catalog/stats`.
- **Repeated demo raises a duplicate-observation error:** This is a known
  issue with `price_engine.demo` when reusing the same fixture source ID.
  Run the demo only once for each new database; **skip it** thereafter.
  Do not delete or reset your database just to fix the demo conflict.
- **Import target not reached:** `--max-rows` counts accepted input rows,
  not unique products. Filtered, invalid and duplicate entries reduce
  `catalog_products`. A true one-million-item count needs enough distinct
  eligible upstream records and a successful bulk import.
- **Download or import fails:** Confirm the file exists and is fully
  downloaded, check free disk space and inspect the local error. The
  official export may be large and the network transfer can fail.
- **AI agent still shows mock headphones prices:** Correct: the root
  `price_agent.py` workflow and catalog are not yet connected.

## Verification and limits

Run these commands **from the `backend/` directory**:

~~~powershell
python -m unittest discover -s tests -v
python -m compileall -q price_engine tests
~~~

**Verified GitHub Actions CI:** [Phase 5 PR #3 run](https://github.com/iam-Seraph/Price-agent/actions/runs/44166599779)
passed **37 backend unittest tests** and Python compilation under Python 3.11.
The tests use illustrative local fixtures, not the upstream bulk export.
They **do not** prove a million-row import or low-latency queries at that
scale. Strict mypy, Hypothesis, licensed retailer price sourcing and
production load benchmarks remain unverified. Inspect the real import count
and measure disk/query performance on your own machine.

The root price_agent.py remains a separate mock-data Groq ReAct prototype.
Its USD prices are NOT linked to the real open catalog. Actual retailer
pricing and authorized retailer adapters remain future work. Do not expose
this unauthenticated local dashboard publicly without security upgrades.
