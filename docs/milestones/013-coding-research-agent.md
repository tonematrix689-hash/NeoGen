# Milestone 013 — Coding and Research Agent

## Outcome

NeoGen can inspect an authorized source workspace, research public web sources, preview exact
multi-file changes, apply an approved change set, run verification through the existing guarded
terminal, and restore a generated recovery checkpoint.

`GENESIS_WORKSPACE_DIR` selects the authorized application checkout. `GENESIS_DATA_DIR` keeps
memory, approvals-related runtime data, and checkpoints separate from that source tree.

## Capability contract

1. `coding.inventory` maps readable UTF-8 source files while excluding common dependency, cache,
   runtime-state, and Git metadata directories.
2. `coding.read` returns content with a SHA-256 version token.
3. `coding.propose` creates a unified diff and a single-use approval tied to the exact paths,
   contents, and inspected file versions.
4. `coding.apply` rejects stale source, consumes the approval, creates a checkpoint, and uses atomic
   file replacement. A failed multi-file application restores the checkpoint automatically.
5. `coding.restore` requires a separate approval and can return every affected file to its original
   state.
6. `research.search` and `research.read` each require explicit approval. Responses are size-bounded,
   HTTPS-only, and marked `untrusted_external`.
7. Verification commands continue through `terminal.run`; deployment, publishing, dependency
   installation, credentials, purchases, and account actions are not implicitly authorized.

## Security boundaries

- Workspace escapes and cross-project approvals are rejected.
- Local, private, reserved, and link-local web destinations are rejected, including redirects.
- Web pages are data, not agent instructions; downloaded content is never executed.
- Source writes are limited by file count and byte budget.
- A proposal is invalidated when a file changes after inspection.
- NeoGen creates no push, release, deployment, or store-publishing capability in this milestone.

## Intended agent loop

The model receives inventory and selected file content, asks the user to approve research when
current external knowledge is needed, produces an inspectable change proposal, waits for approval,
applies it, and requests appropriate verification commands. It reports test output and the recovery
checkpoint before any separately authorized publication step.
