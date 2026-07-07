# AGENTS.md

## Scope

This file applies to the entire repository.

## Required reading

Before editing, read:

1. `README.md`
2. `docs/STATUS.md`
3. `docs/NEXT.md`

## Purpose

This repository is a **frozen local video workflow prototype**.

It may contain scaffold material for subtitles, silence cutting, rendering preparation, scripts, and project structure.

It is not RTS core.

It is not RTS-AGE.

It is not a production publishing pipeline.

It is not an automatic upload system.

## Hard boundaries

- Do not add automatic upload or publishing behavior.
- Do not add platform automation.
- Do not add credentials, API keys, tokens, secrets, or private links.
- Do not add customer media, private video material, or copyrighted source media.
- Do not add background processing services or unattended execution workflows.
- Do not add impersonation or deceptive media workflows.
- Do not turn this repository into RTS core, RTS-AGE, or production infrastructure.

## Media handling

Treat media inputs, generated subtitles, temporary files, and rendered outputs as local review artifacts unless explicitly reviewed otherwise.

Before adding or referencing media, consider:

- source rights
- privacy
- public-use permission
- generated subtitle accuracy
- whether output could be mistaken as published or approved content

## Freeze boundary

Treat the next pass as freeze review and video-flow inventory, not expansion.

If an item implies automatic publishing, platform automation, unattended execution, sensitive media, or public use of unreviewed assets, mark it as `RISKY` and do not expand it.

If this repository is not needed for current work, leave it frozen.

## Change style

- Keep documentation lightweight and explicit.
- Prefer additive edits; avoid destructive rewrites.
- Prefer review-boundary documentation over implementation.
- Do not rewrite scripts unless there is a concrete video-workflow task.

## Validation

For documentation-only changes, report changed files and confirm that no media files, credentials, automatic publishing, platform automation, background service, unattended execution workflow, or production behavior was added.
