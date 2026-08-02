# Genesis / Afterlife Neogenesis

Genesis is an AI operating system kernel built around services, capabilities, and applications.

The kernel owns runtime startup, shutdown, logging, events, dependency injection, service discovery,
lifecycle orchestration, and health reporting. AI providers, memory, permissions, filesystems,
terminals, and desktop applications are capabilities or services layered on top of the kernel.

Afterlife Neogenesis is the first player-facing application built on Genesis. The current MVP is a
local, dependency-free vertical slice with a landing page, dashboard, deterministic VERA companion,
player state, wallet placeholders, governance messaging, health checks, and automated tests.

## Requirements

- Python 3.11 or newer

## Install

```powershell
python -m pip install -e .
```

## Run the Genesis kernel

```powershell
genesis
```

Or:

```powershell
python -m genesis.app.kernel.main
```

## Run the Afterlife Neogenesis MVP

```powershell
afterlife-mvp
```

Or:

```powershell
python -m genesis.apps.afterlife.server
```

Then open:

```text
http://127.0.0.1:4173
```

Available routes:

- `/` — public landing page
- `/dashboard` — member dashboard shell
- `/health` — health check
- `/api/state` — demonstration player state
- `/api/vera` — deterministic VERA guidance endpoint

The MVP does not claim to be a hosted production service. Wallet balances and inventory are local
demonstration data. Production AI routing, authentication, persistence, ACoin settlement, marketplace,
3D avatar tooling, and RPG systems remain separate future milestones.

## Test

```powershell
python -m unittest discover -s tests -v
```

## Package build

```powershell
python -m pip install --upgrade build
python -m build
```

## Current architecture

```text
NeoGen
├── Genesis AI Kernel
│   ├── Runtime lifecycle
│   ├── Dependency injection
│   ├── Event bus
│   ├── Service discovery
│   ├── Health and diagnostics
│   └── Future memory, permissions, agents, workflows, models, and plugins
├── Afterlife Neogenesis MVP
│   ├── Landing page
│   ├── Dashboard
│   ├── VERA companion endpoint
│   ├── Player snapshot
│   ├── Wallet and inventory placeholders
│   └── Governance-first interaction model
└── Future ACoin integration
    ├── Wallets
    ├── Double-entry ledger
    ├── NEO and Essence
    ├── Rewards
    └── Marketplace settlement
```
