# Genesis / Afterlife Neogenesis

Genesis is an AI operating system kernel built around services, capabilities, and applications.

The kernel owns runtime startup, shutdown, logging, events, dependency injection, service discovery,
lifecycle orchestration, and health reporting. AI providers, memory, permissions, filesystems,
terminals, and desktop applications are capabilities or services layered on top of the kernel.

Afterlife Neogenesis is the first player-facing application built on Genesis. The current MVP is a
local, dependency-free vertical slice with a landing page, dashboard, deterministic VERA companion,
player state, wallet placeholders, governance messaging, health checks, and automated tests.

## AI assistant capabilities

Milestone 011 adds durable, project-scoped memory and conversation context. The standard-library
SQLite implementation is inspectable, portable, and registered through the kernel lifecycle.

Milestone 012 provides the backend for the post-login workspace. `create_workspace_runtime()`
composes memory, consent, workspace-scoped files, shell-free terminal execution, and a UI-facing
workspace service. File writes and terminal commands require a matching single-use approval.

Milestone 013 adds an authorized coding-and-research loop. NeoGen can inventory source, bind edits
to inspected SHA-256 versions, show unified diffs, create recovery checkpoints, restore changes, and
research public HTTPS sources. Search and page reads require single-use consent, external content is
marked untrusted, and local/private network access is blocked. Publishing remains a separate action.

Milestone 014 adds project-scoped adaptive learning and test-gated self-improvement. NeoGen learns
from bounded success/failure outcomes without storing prompts or code, ranks strategies with an
inspectable online-learning score, and can improve an authorized app or its own selected source.
Every diff and verification command requires approval; failed checks automatically restore the
recovery checkpoint. See `docs/milestones/014-adaptive-self-improvement.md` for research and limits.

The tablet client is Puter-first for browser identity, AI inference, cloud conversation backups,
settings, and optional static hosting. It loads Puter.js v2 directly and does not require NeoGen to
store a model-provider API key. Local repository writes and terminal commands deliberately remain
behind the Genesis runtime: the browser requests a visible, exact-action approval and the runtime
consumes that approval once. A Puter-hosted frontend therefore remains useful on its own for AI and
cloud data, but it cannot silently acquire shell access to the user's device.

The redesigned tablet experience uses a conversation-first interface with persistent local and
Puter-backed history, dynamic model selection, responsive navigation, Monaco editing, repository
inspection, command-center analytics, Academy, capability management, settings, and the expanding
Afterlife world. The Neo composer exposes Puter chat and multimodal analysis, image and video
generation, OCR, text-to-speech, transcription, and speech-to-speech conversion. Puter function
calling can inspect NeoGen health, source, Git, and cloud files; any requested file write, terminal
command, Git mutation, cloud note, or publication still pauses for visible exact-action approval.

The Agent Council can attach a bounded, visible snapshot of the authorized Git checkout to every
ten-specialist round. Later specialists cross-analyse the same repository evidence and shared
transcript before the synthesis lead produces a decision. The result can be handed to Neo as a
governed improvement proposal or saved under `docs/agent-council/`; source edits, verification,
commits, pushes, and merges remain separate exact, single-use approvals.

The public client now presents NeoGen through a silica-core visual system and a subscription
catalogue with ten cumulative individual levels, role-assigned Admin Level 11 and Owner Level 12,
plus Business and Enterprise plans. Every plan and ability remains visible in Settings, including
locked and provider-dependent options, so users can understand the complete capability path. The backend
persists active entitlements and pending plan requests without accepting payment credentials.
Level 1 activates automatically; paid requests remain pending until an explicitly configured
billing provider or an administrator confirms activation, so the interface never mistakes a plan
selection for a completed charge.

When the configured workspace is a Git checkout, NeoGen also exposes repository status, history,
diffs, branches, commits, fetches, pushes, merges, and other Git operations. Inspection is read-only;
every Git mutation is executed without a command shell and requires a matching one-time approval.
Remote operations use credentials already configured for Git on the device. Do not put GitHub
tokens in `web/`, Puter KV, Puter Files, command arguments, or repository source. For hosted GitHub
API operations, use a repository-scoped GitHub App with short-lived installation tokens.

To point the composed workspace runtime at an authorized application checkout, set
`GENESIS_WORKSPACE_DIR` to that repository. NeoGen stores memory and recovery checkpoints under
`GENESIS_DATA_DIR`, keeping runtime state separate from source code.

```powershell
$env:GENESIS_WORKSPACE_DIR = "C:\path\to\your\app"
$env:GENESIS_DATA_DIR = "$env:LOCALAPPDATA\NeoGen"
```

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
demonstration data. Production AI routing, authentication, ACoin settlement, marketplace, 3D avatar
tooling, and further RPG systems remain separate milestones.

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
│   └── Memory, permissions, tools, research, learning, and guarded improvement
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
