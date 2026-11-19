# Price Agent documentation

Start at the [repository README](../README.md) for current setup, features and CLI commands. This directory keeps **current guides** separate from **historical engineering checkpoints**.

## Guides

- [Open Food Facts catalog import](guides/open-food-facts-catalog.md) — source, license, import commands, actual-count limitations.
- [Local data workspace](guides/data-workspace.md) — CSV/JSON/XLSX upload, provider lookup, and compatibility notes (historical overlay guide).
- [Virtual Intelligence Studio](guides/virtual-intelligence-studio.md) — fictional virtual products, worker architecture and UI controls.
- [Backend implementation](../backend/README.md) — modules, database, API and tests.
- [Static site](../site/README.md) — portfolio/demo website.
- [Offline end-to-end validation](guides/offline-validation.md) — full automated check command, test coverage and live-service limitations.

- [Phase 11 — API configuration and controlled learning](phases/phase-11-configuration-and-learning.md) — opt-in preferences, source evidence separation and key setup.

## Architecture and audit

- [Single-operator security boundary](architecture/single-operator-security.md) — no real authentication or tenant isolation yet.
- [Historical hardening audit](audits/legacy-hardening.md) — preserved early benchmarks and limitations; treat early status statements as historical.

## 100 engineering checkpoints (Phases 1–10)

| Phase | Loops | Document |
| --- | --- | --- |
| 1 | 1–10 | [Source-attributed provider foundation](phases/phase-01-provider-foundation.md) |
| 2 | 11–20 | [Ingestion and validation safety](phases/phase-02-ingestion-safety.md) |
| 3 | 21–30 | [Verified-offer dashboard](phases/phase-03-verified-dashboard.md) |
| 4 | 31–40 | [Price watches and opt-in monitor](phases/phase-04-price-watches.md) |
| 5 | 41–50 | [Source-qualified alerts](phases/phase-05-alerts.md) |
| 6 | 51–60 | [Unified workspace and controls](phases/phase-06-workspace-integration.md) |
| 7 | 61–70 | [Stored-offer price research](phases/phase-07-price-research.md) |
| 8 | 71–80 | [Deterministic command assistant](phases/phase-08-command-assistant.md) |
| 9 | 81–90 | [Historical price intelligence](phases/phase-09-historical-intelligence.md) |
| 10 | 91–100 | [Local release audit and security headers](phases/phase-10-release-hardening.md) |

**Naming note:** The older Open Food Facts catalog was also called “Phase 5”; its [catalog guide](guides/open-food-facts-catalog.md) is **separate** from the later **Phase 5 alerts (loops 41–50)** milestone. They are not the same release. Historical branch/merge IDs remain in the archived reports.

## Conventions

- Lowercase **kebab-case** Markdown filenames, grouped by purpose.
- Python modules, SQL migrations, tests, dashboard assets and root CLI entry points keep their established names to avoid breaking imports and commands.
- Relative links from each documentation page should resolve from that page's directory.
- Never add secrets, downloaded product exports, or local databases to source control.
