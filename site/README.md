# Price Agent — standalone website

A responsive, static project landing page generated from the currently merged documentation in [iam-Seraph/Price-agent](https://github.com/iam-Seraph/Price-agent).

## Contents

- `index.html` — page content and semantic structure
- `style.css` — responsive dark/teal design, no external dependencies
- `script.js` — accessible tabs, copyable commands, mobile menu
- `favicon.svg` — site icon

## Preview locally

Run from this folder:

```powershell
python -m http.server 8080
```

Open <http://127.0.0.1:8080> in your browser. It also works by opening `index.html` directly, but clipboard access may depend on browser permissions.

## Publishing

Upload these static files to a site host or an editor that accepts HTML/CSS/JS sources. This package **is not yet published through ChatGPT Sites** and does not include a Sites project link. Do not add private `.env` keys, SQLite databases, or user records to this public-facing site.

## Data and accuracy

- 37/37 backend tests were verified through GitHub Actions.
- The "1M" metric is an accepted-row import target, not an actual product count.
- Open Food Facts chiefly covers food/grocery metadata, not prices or a general electronics catalog.
- No server-side product search, live retailer quotes, or API calls are present in this standalone static site.
- The real Price Agent dashboard runs **locally** through FastAPI, not as part of this static landing page.

For project details and licensing, read the repository `README.md`, `PHASE5.md`, and `AUDIT.md`.
