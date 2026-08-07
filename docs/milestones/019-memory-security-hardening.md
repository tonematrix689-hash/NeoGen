# Milestone 019 — Memory and security hardening

NeoGen now treats persistent memory and autonomous source access as privileged, bounded capabilities.

## Security controls

- Guarded repository, source, terminal, approval, and decision-symbiosis routes require the Owner role.
- Cross-origin API access is denied by default. Deployments may explicitly allow trusted origins with `NEOGEN_ALLOWED_ORIGINS` as a comma-separated list.
- Authentication endpoints are throttled per client to reduce automated password guessing.
- API and tablet responses emit no-store, anti-sniffing, anti-framing, and referrer-protection headers.
- Unexpected exceptions return generic messages rather than file paths, internal types, or sensitive details.
- A signed-in user can revoke every active session after suspected compromise.

## Memory controls

- Project, conversation, decision, context, outcome, query, and result-limit bounds prevent unbounded persistence and retrieval.
- Searches and lifecycle operations remain owner/project scoped at the database query boundary.
- `forget_project` atomically deletes one owner's project memories, conversation turns, and decisions while preserving other owners' records.
- Revoked decisions remain excluded from active recall unless explicitly requested for audit.

These controls reduce cross-user leakage, memory poisoning, denial-of-service, token exposure, and unauthorized self-editing risks. They do not replace TLS, encrypted production storage, external penetration testing, monitored backups, or an independently reviewed deployment configuration.
