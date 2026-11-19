# Single-operator boundary and multi-user migration plan

## Current status (Loops 91–100)

Price Agent is NOT multi-user. It is a loopback-only, single-operator development service. Shared SQLite watch rules, alert state, provider history, and workspace data must not be exposed on the public internet or a multi-user LAN without a separate identity and authorization design.

Enforced today:
- CLI server binds only to 127.0.0.1, localhost or ::1.
- Local verified write routes require same-origin browser requests; cross-site requests are rejected.
- TrustedHost middleware restricts Host headers.
- Verified UI and API send no-store, no-sniff, anti-framing and referrer protections.
- Historical intelligence, research and audit routes never fetch new provider prices.
- Explicit human approval is required before saving natural-language watches; monitoring/delivery remain separately initiated.

Still required before any true multi-user deployment:
1. Add a proven authentication provider with session lifecycle, login throttling, password reset or federated identity, and CSRF tokens.
2. Introduce tenant and account tables with foreign keys and irreversible migrations.
3. Scope every query, watch, alert, contact, provider credential and audit record to the authenticated tenant.
4. Enforce authorization on each API route, not only in the web UI; prevent cross-tenant ID enumeration.
5. Ensure background workers carry tenant context and cannot dispatch another tenant's messages.
6. Set configurable quotas, secret rotation, retention/deletion and privacy policy.
7. Use migration backups, concurrency tests, cross-tenant isolation tests, security review and deployment monitoring.
8. Replace development-only local middleware with production TLS and secure reverse proxy settings.

No fake login or authorization placeholder is enabled. Authentication and tenant isolation remain future work. A passing SQLite integrity audit only checks existing local evidence data, not service security or third-party merchant truthfulness.
