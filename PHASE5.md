# Phase 5 — real product catalog (target: 1,000,000)

This phase adds a separate local product-identities catalog to Price Agent.
It supports importing up to one million rows per invocation from an official
Open Food Facts bulk export; it does NOT ship one million records in GitHub.
Real imported product counts are reported by the importer and the stats API.
No generated products or prices are shipped.

## Source, license and scope

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

Start from the repository root on the Phase 5 feature branch.

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
- Skips records without valid numeric 8–14-digit codes or product names.
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

## Verification and limits

~~~powershell
cd backend
python -m unittest discover -s tests -v
python -m compileall -q price_engine tests
~~~

Continuous integration runs backend tests on pull requests. Tests use
illustrative tiny fixtures, not real bulk data. They DO NOT prove a
million-row import or its latency. Verify local import row count, disk usage,
query performance and data-license obligations after downloading.

The root price_agent.py remains a separate mock-data Groq ReAct prototype.
Its USD prices are NOT linked to the real open catalog. Actual retailer
pricing and authorized retailer adapters remain future work. Do not expose
this unauthenticated local dashboard publicly without security upgrades.
