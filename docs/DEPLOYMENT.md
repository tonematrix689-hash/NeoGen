# NeoGen Website Publishing Guide

NeoGen is deployable as a single persistent container. The production entrypoint serves the
web client and API on one origin, stores SQLite data on a durable volume, exposes a health check,
and disables legacy direct-mutation API routes. Files, terminal operations, Git changes, and
publishing remain behind the guarded single-use approval contracts.

## Required infrastructure

- A container host with HTTPS and a persistent disk mounted at /var/lib/neogen
- A production domain
- Backups for the persistent disk, with a tested restore procedure
- Secret environment configuration supplied by the host, never committed to Git

The included render.yaml is a starting blueprint for a persistent Render web service. Equivalent
Docker hosting is supported when it supplies the same volume, environment, TLS, and health check.

## Required configuration

Set these before launch:

- NEOGEN_OWNER_EMAIL
- NEOGEN_ALLOWED_ORIGINS to the exact HTTPS site origin
- NEOGEN_OPERATOR_LEGAL_FORM
- NEOGEN_OPERATOR_REGISTRATION
- NEOGEN_OPERATOR_JURISDICTION
- NEOGEN_OPERATOR_ADDRESS
- NEOGEN_GOVERNING_LAW
- NEOGEN_SUPPORT_EMAIL
- NEOGEN_PRIVACY_EMAIL
- NEOGEN_SECURITY_EMAIL
- NEOGEN_HOSTING_REGIONS
- NEOGEN_PAYMENT_PROVIDER when commerce is enabled

The placeholder values in web/.well-known/security.txt must be replaced with the production
domain and a staffed security mailbox before public launch.

## Local production verification

```bash
docker build -t neogen:release .
docker volume create neogen-data
docker run --rm -p 8080:8080 \
  -v neogen-data:/var/lib/neogen \
  -e NEOGEN_HTTPS=0 \
  -e NEOGEN_OWNER_EMAIL=owner@example.com \
  neogen:release
```

Open http://127.0.0.1:8080/ and verify:

1. /api/v1/health returns HTTP 200.
2. Registration, legal acceptance, login, logout, and account-wide session revocation work.
3. Conversations and settings survive a container restart.
4. A direct POST to /api/v1/terminal/execute is rejected with HTTP 403.
5. The guarded workspace requires a matching, approved, single-use action.
6. Mobile navigation, offline shell, legal centre, and accessibility keyboard paths work.
7. Backups restore successfully to a clean instance.

## Release boundary

A technical beta may launch after CI, live smoke tests, backups, monitoring, and contacts are
configured. Public payment collection must remain disabled until the legal launch checklist,
merchant/payment configuration, consumer terms, tax handling, and market-specific review are
complete. Catalogued providers and Cognitive Matrix capabilities must not be represented as active
until their adapters and health checks exist.

## Publish sequence

1. Merge the production pull request only after all required checks pass.
2. Create the hosting service from render.yaml or the Dockerfile.
3. Add the persistent disk and environment values.
4. Replace security.txt placeholders.
5. Deploy the exact tested commit.
6. Run the verification list above against the HTTPS domain.
7. Record the release commit, configuration owner, backup result, and rollback target.
