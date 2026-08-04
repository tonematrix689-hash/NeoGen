# Milestone 014 — Adaptive, Test-Gated Self-Improvement

## Outcome

NeoGen can learn which approved strategies perform well, prepare improvements to an authorized
application or its own source tree, expose the complete diff and verification commands for consent,
execute only a fully approved bundle, and automatically restore its checkpoint when any check fails.

This is controlled self-improvement. It is not silent self-modification, automatic publishing,
credential use, security bypass, or device replication.

## Research basis

- [scikit-learn incremental learning](https://scikit-learn.org/stable/computing/scaling_strategies.html)
  describes streamed observations, feature extraction, and incremental algorithms as the three
  parts of online learning. NeoGen therefore stores small outcome observations instead of retaining
  prompts or retraining an opaque model after every action.
- [PyTorch reproducibility guidance](https://docs.pytorch.org/docs/stable/notes/randomness.html)
  explains that results can vary by release and platform and recommends controlling randomness and
  deterministic behavior for regression testing. NeoGen's initial adaptive scorer is deterministic,
  inspectable, and verified through explicit commands.
- [The Update Framework metadata model](https://theupdateframework.io/docs/metadata/) separates
  root, targets, snapshot, and timestamp trust, with signed metadata, hashes, sizes, versions, and
  expiry. NeoGen does not treat arbitrary web content as an installable update; a future unattended
  release updater must use equivalent trusted metadata verification.
- [GitHub release API documentation](https://docs.github.com/en/rest/releases/releases) exposes
  release channels and SHA-256 asset digests. Release discovery may inform a proposal, but never
  authorizes installation by itself.

## Adaptive learning

`LearningService` stores only these bounded fields:

- project identifier
- task kind
- strategy identifier
- reward from 0.0 to 1.0
- source category (`user`, `verification`, or `system`)
- timestamp

It intentionally does not store prompts, source code, terminal output, credentials, or retrieved
web pages. Strategies are ranked with an upper-confidence-bound score so successful choices are
favored while unseen choices receive controlled exploration. Every project is isolated in SQLite.

## Self-improvement transaction

1. Inspect files and capture their SHA-256 versions.
2. Research approved HTTPS sources when current information is necessary.
3. Prepare a complete multi-file diff and bounded list of verification commands.
4. Present separate, exact single-use approvals for the code change and every command.
5. Refuse execution unless the entire bundle is approved.
6. Create a recovery checkpoint and apply atomic writes.
7. Run verification without a command shell.
8. On any exception, timeout, or non-zero exit, restore the checkpoint immediately.
9. Record a content-free success or failure outcome for future strategy ranking.

Automatic recovery is tied to hashes captured immediately after application. If another process
changes an affected file while verification is running, NeoGen refuses to overwrite that newer
content and reports a recovery conflict for human resolution.

## Boundaries

- Self-improvement can target NeoGen only when the owner selects NeoGen as
  `GENESIS_WORKSPACE_DIR`.
- Stale source, substituted content, changed commands, path escapes, cross-project approvals, and
  partially approved bundles are rejected.
- A successful local improvement does not grant permission to commit, push, deploy, release,
  purchase, message, or alter accounts.
- Fully unattended release installation remains disabled until trusted metadata signatures are
  verified by a dedicated updater implementation.
