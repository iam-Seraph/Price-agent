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

- Three Phase 10 regression workflows passed in GitHub Actions; historical Phase 5 documentation separately records its earlier 37-test result.
- The "1M" metric is an accepted-row import target, not an actual product count.
- Open Food Facts chiefly covers food/grocery metadata, not prices or a general electronics catalog.
- This standalone static site does not itself make product/provider API calls. The **separate local Python workspace** can request provider-reported offers when configured.
- The real Price Agent dashboard runs **locally** through FastAPI, not as part of this static landing page.

For project details and licensing, read the repository `README.md`, `docs/README.md`, `docs/guides/open-food-facts-catalog.md`, and `docs/audits/legacy-hardening.md`.
