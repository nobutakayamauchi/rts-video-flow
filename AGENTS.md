# AGENTS.md

## Scope

This file applies to the entire repository.

## Required reading

Before editing, read:

1. `README.md`
2. `docs/STATUS.md`
3. `docs/NEXT.md`
4. `docs/SECURITY_COST_APPROVAL_FLOW.md`

## Purpose

This repository is a smartphone-first video workflow prototype and reviewable implementation area for local media preparation, narration, composition, and explicitly approved emergency overflow rendering.

It is not RTS core.

It is not RTS-AGE.

It is not an automatic publishing pipeline.

It is not an automatic upload system.

It is not a general-purpose unattended media-processing service.

## Mandatory execution order

Any path that accepts untrusted content, can spend money, can mutate an external system, or can trigger consequential execution must enforce:

```text
Security Gate
→ Cost / Consequence Gate
→ Explicit Single-Use Approval
→ Scoped Execution
→ Outcome Verification + Audit
```

The Security Gate always runs first. Unknown or uninspectable input fails closed.

## Security Gate requirements

Treat all of these as untrusted:

- image, video, audio, document, archive, and structured-data contents
- file names, paths, extensions, MIME declarations, and metadata
- manifests, prompts, text instructions, URLs, environment references, and command arguments

Required controls:

- allowlisted formats and schemas
- actual structure/MIME verification
- hard size, resolution, duration, stream, frame-rate, recursion, decompression, and timeout limits
- internally generated safe names and normalized paths
- no shell interpolation of untrusted values
- active content, attachment streams, unnecessary metadata, and external references rejected or removed
- inspection with least privilege, no secrets, and no unnecessary network access
- accepted content hash recorded and rechecked immediately before execution
- safe constrained re-encoding where practical
- ambiguous, invalid, timed-out, or uninspectable content rejected or quarantined

A Security Gate pass means only that implemented controls passed. It is not a guarantee against every unknown threat.

## Cost and approval requirements

After Security Gate pass, show the provider, project/account, region, operation, input/output volume, CPU, memory, model/API, maximum runtime, parallelism, retries, transfer/storage assumptions, external consequences, and estimated monetary ceiling.

Defaults:

- task count and parallelism: 1
- automatic retry: off
- bounded runtime and input size
- no automatic paid fallback
- no hidden schedule

Approval must be explicit, one-shot, time-limited, content-hash-bound, provider-bound, parameter-bound, and consequence-bound. Any material change invalidates approval.

## Emergency overflow compute

Oracle remains the normal UI, editing, control, and lightweight processing environment.

Google Cloud or another external worker may be used only as a manually selected emergency overflow path when the normal environment cannot finish a heavy render safely.

This limited exception is allowed only when:

- the full Security → Cost → Approval sequence passed
- execution is one task with no automatic retry by default
- the exact input hashes and parameters are fixed
- the worker is isolated from primary UI availability
- there is no automatic fallback or recurring schedule
- output and actual cost are verified afterward

The exception does not authorize general background services or unattended expansion.

## Hard boundaries

- Do not add automatic upload or publishing behavior.
- Do not add platform automation.
- Do not add credentials, API keys, tokens, secrets, or private links.
- Do not add customer media, private video material, or copyrighted source media.
- Do not add general-purpose background processing or unattended workflows.
- Do not add automatic paid fallback.
- Do not add automatic retries or parallel paid execution without a new explicit decision.
- Do not add impersonation or deceptive media workflows.
- Do not turn this repository into RTS core, RTS-AGE, or general production infrastructure.

## Media handling

Treat media inputs, generated subtitles, temporary files, and rendered outputs as review artifacts unless explicitly reviewed otherwise.

Before adding or referencing media, consider:

- source rights
- privacy
- public-use permission
- generated subtitle accuracy
- malicious or malformed content risk
- resource-exhaustion risk
- whether output could be mistaken as published or approved content

Untrusted uploads must enter quarantine or a local inspection path before the approved input prefix or execution environment.

## Freeze boundary

The repository may receive narrow, concrete video-workflow fixes and the gated emergency overflow implementation described above.

Broad publishing automation, platform automation, recurring jobs, automatic external execution, sensitive media handling, or public use of unreviewed assets remains `RISKY` and must not expand without a separate decision.

## Change style

- Keep changes small, explicit, and reviewable.
- Prefer narrow implementation and tests over broad infrastructure expansion.
- Preserve rollbackability.
- Update documentation when architecture or gate order changes.
- Do not describe a submitted job as completed until output and logs are verified.

## Validation

For implementation changes:

- test Security Gate allow and reject paths
- test missing, expired, changed, and mismatched security evidence
- test Cost Gate and approval refusal paths
- test duplicate-execution prevention
- verify no paid or external execution occurred unless explicitly approved in the current task
- report changed files, tests, external resources changed, known cost, and residual risk

For documentation-only changes, report changed files and confirm that no media files, credentials, automatic publishing, platform automation, paid execution, or external mutation was added.
