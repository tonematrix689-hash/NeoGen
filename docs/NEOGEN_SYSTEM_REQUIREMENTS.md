# NeoGen Operating System — Functional Completion Map

NeoGen is currently a Python 3.11+ AI operating-system kernel with configuration, dependency injection, events, service discovery, lifecycle orchestration, logging, health reporting, and a command-line entry point.

This document defines the missing systems required to evolve that kernel into a secure, locally useful AI operating environment.

## 1. Kernel and Runtime

Status: foundation present.

Required completion work:

- Stable runtime state machine and service contracts.
- Capability discovery and versioned manifests.
- Dependency graph validation before startup.
- Crash recovery, supervised service restart, and safe-mode boot.
- Structured diagnostics, metrics, tracing, and error reporting.
- Persistent configuration with schema validation and migrations.
- Cross-platform process, path, signal, and permissions abstractions.

## 2. Identity, Policy, and Governance

Required before autonomous tools are enabled:

- Local user identity and device identity.
- Role-based and capability-based authorization.
- Consent receipts for sensitive operations.
- Policy decision engine with allow, deny, ask, and sandbox outcomes.
- Immutable audit records with integrity verification.
- Emergency stop, autonomy limits, rate limits, and resource budgets.
- Data classification, retention, export, deletion, and backup policy.
- Explainable records for consequential AI decisions.

## 3. AI Orchestration Layer

- Provider-neutral model interface.
- Local and remote model adapters.
- Model capability registry and routing policy.
- Prompt templates, versioning, and injection defenses.
- Conversation state and context-window management.
- Tool-call planner with validation and bounded retries.
- Structured outputs and schema validation.
- Evaluation harness for quality, safety, latency, and cost.
- Offline fallback behavior when no model is available.

## 4. Memory and Knowledge

- Session memory.
- User-approved long-term memory.
- Project-scoped memory.
- SQLite metadata store.
- Document ingestion and chunking.
- Embedding provider abstraction and vector index.
- Semantic and keyword retrieval.
- Provenance, citations, confidence, expiration, and version history.
- Encryption at rest and per-user access controls.
- Memory review, correction, deletion, export, and consolidation.

## 5. Tool and Plugin Platform

Every tool must expose a manifest containing its name, version, permissions, input schema, output schema, risks, supported platforms, and health check.

Initial tools:

- Read, create, update, move, and delete files.
- Workspace-scoped code editing.
- PowerShell, CMD, Bash, and terminal execution.
- Git and GitHub workflows.
- Python task execution.
- Browser and web research.
- Application launching.
- Clipboard and notification access.
- Email and calendar adapters.

Execution requirements:

- Workspace boundaries and path canonicalization.
- Command allowlists and denylists.
- Sandboxed execution where available.
- Time, CPU, memory, output, and network limits.
- Human confirmation for destructive or high-impact actions.
- Complete audit trail and reversible operations where possible.

## 6. User Environment

- Desktop chat interface.
- Project/workspace selector.
- File browser and editor.
- Terminal panel.
- Task activity and approval center.
- Memory and permission management screens.
- Diagnostics and recovery screen.
- Accessible keyboard navigation and screen-reader semantics.
- Local API for UI-to-kernel communication with authentication.

## 7. Automation and Agent Runtime

- Durable task queue.
- Scheduled and event-triggered jobs.
- Checkpointing and resumable workflows.
- Dependency-aware task graphs.
- Human approval gates.
- Idempotency and duplicate prevention.
- Concurrency controls and cancellation.
- Resource quotas and budget enforcement.
- Clear distinction between recommendations and executed actions.

## 8. Storage and Data Services

- SQLite for initial local persistence.
- Repository interfaces so storage can later migrate.
- Transaction handling and migrations.
- Secret storage through the operating system credential vault.
- Encrypted backups and restore verification.
- File indexing and change detection.
- Data corruption detection and recovery.

## 9. Networking and Integration

- HTTP client abstraction with timeouts, retries, and certificate validation.
- Optional local-only mode.
- Explicit per-plugin network permissions.
- Proxy configuration.
- API credential management without plaintext secrets in source control.
- Webhook and event adapters.
- Update channel with signed release verification.

## 10. Testing and Delivery

- Unit, integration, security, and end-to-end tests.
- Windows and Linux CI matrix.
- Static typing, linting, formatting, dependency, and secret scans.
- Reproducible builds and locked dependencies.
- Signed release artifacts and checksums.
- Installation, upgrade, rollback, and uninstall procedures.
- Threat model, architecture decision records, and operator handbook.

## Recommended Delivery Order

1. Repair and freeze kernel contracts.
2. Add policy, permissions, audit, and secret storage.
3. Implement capability manifests and safe file/terminal tools.
4. Add SQLite persistence and memory interfaces.
5. Add model-provider abstraction and one local/mock provider.
6. Build the local API and minimal desktop interface.
7. Add task scheduling, approval workflows, and recovery.
8. Expand integrations only after security and evaluation gates pass.

## Definition of a Functional NeoGen MVP

The MVP is complete when a user can launch NeoGen locally, converse through a desktop or local web interface, select a workspace, ask the assistant to inspect and safely edit files, run approved terminal commands, retain user-approved project memory, review every requested permission and executed action, restart without losing state, and recover safely from model, plugin, or process failure.
