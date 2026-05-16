# Security Hardening Status

This document describes the effective runtime security controls in Phase 10.

## Enforced Controls

- **SELECT-only SQL gate** via `SqlPolicyEngine` (`POL001`..`POL014`)
- **No wildcard projection** (`SELECT *`, `c.*`) while allowing `COUNT(*)`
- **Blocked schemas/functions/features**
  - `sys`, `INFORMATION_SCHEMA`
  - `OPENROWSET`, `OPENQUERY`, `xp_cmdshell`, ...
  - profile-driven `blocked_sql_features`
- **Allow-list enforcement**
  - `allowed_schemas`
  - `allowed_tables`
- **Row-filter enforcement**
  - profile `row_filters` are required when the user's group matches `applies_to_groups`
- **PII/sensitive/secret column checks** via `PiiPolicyEngine`
- **Read-only DB access intent**
  - ODBC connection string uses `ApplicationIntent=ReadOnly`

## Not Yet Enforced (Known Gaps)

- **Masking at query-result level**
  - `masking_rules` are stored in profile policy and surfaced in context/readiness, but result-level masking is not applied in `MssqlRunner` yet.
- **Automatic SQL rewrite for row filters**
  - the engine currently validates presence of required predicates; it does not inject them automatically.

## Recommended Production Setup

- Use dedicated SQL read-only account in `.env` (`DB_USERNAME`/`DB_PASSWORD`)
- Keep `DB_TRUST_SERVER_CERTIFICATE=false` in production
- Set `USER_RESOLVER_MODE=header` behind trusted gateway
- Restrict network path from API host to SQL Server
- Enable centralized log shipping for policy violations and query audits
