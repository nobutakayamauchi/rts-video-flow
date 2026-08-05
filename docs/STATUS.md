# rts-video-flow Status

Status: ACTIVE NARROW IMPLEMENTATION / SECURITY-GATED EMERGENCY OVERFLOW / REVIEW BEFORE EXECUTION

## Current position

This repository is a smartphone-first Vlog workflow prototype with an active narrow implementation for:

- iPhone media intake
- project and timeline editing
- timed post-recorded narration
- local review and composition
- local/Oracle rendering where capacity permits
- manually approved emergency overflow rendering when Oracle cannot finish safely

It is not RTS core.

It is not RTS-AGE.

It is not an automatic publishing pipeline.

It is not a general unattended media-processing service.

## Architecture decision

Oracle remains the normal control plane and UI.

Google Cloud is a manually selected emergency overflow path only. It was introduced after the Oracle service was killed by the OOM killer during rendering. The external worker prevents heavy FFmpeg work from taking down the primary UI.

The overflow path must never become an automatic fallback.

## Mandatory gate state

The required order is:

```text
Security Gate
→ Cost / Consequence Gate
→ Explicit Single-Use Approval
→ Scoped Execution
→ Outcome Verification + Audit
```

Implemented in the branch:

- `scripts/media_security_gate.py`
- `scripts/cloud_cost_gate.py`
- `cloud_render/worker.py`
- `tests/test_media_security_gate.py`
- `tests/test_cloud_cost_gate.py`
- `docs/SECURITY_COST_APPROVAL_FLOW.md`

## Google Cloud resources already created

- project: `rts-vlog-render`
- region: `asia-northeast1`
- bucket: `rts-vlog-render-files-20260805`
- Artifact Registry repository: `rts-vlog-render`
- Cloud Run Job: `rts-vlog-render`
- previous image tag: `cost-gated-v1`

The previous image was built before the Security Gate hardening. It must not be used for production or untrusted input. A new image build requires a new explicit cost approval.

## Security controls now represented in code

- allowlisted media suffixes
- regular-file and non-symlink requirement
- safe internal ASCII filename requirement
- 512 MiB per-file limit
- ffprobe timeout
- stream-type and stream-count limits
- resolution, duration, and frame-rate limits
- SHA-256-bound SECURITY_PASS
- Cost Gate refusal without a current matching pass
- GCS bucket and prefix allowlist
- downloaded-input hash revalidation
- no shell interpolation
- FFmpeg stdin disabled
- one render thread
- render timeout
- metadata and chapters removed
- existing output object overwrite refusal

## What is verified

- original Cloud Build pipeline can build and push a container
- Artifact Registry contains the previous image
- Cloud Run Job definition exists and is Ready
- Cost Gate baseline tests previously passed before Security Gate integration
- documentation and code changes are committed to the feature branch

## What is not yet verified

- the new Security Gate tests on Oracle
- real ffprobe behavior against generated safe and malformed samples
- new container image build
- Cloud Run Job image update
- end-to-end Security Pass → Cost Approval → GCS → Cloud Run → output flow
- actual runtime cost of the minimal secured render
- cleanup and approval-consumption behavior

## Prohibited until verification

- executing the current Cloud Run Job with untrusted or real user media
- automatic paid fallback
- automatic retries
- recurring schedules
- public upload or publishing
- customer/private/copyrighted media
- claiming the secured cloud render is complete

## Completion condition

The emergency overflow path is not complete until:

1. local Security and Cost Gate tests pass;
2. safe and reject sample tests pass;
3. a newly approved image build succeeds;
4. the Job is updated without execution;
5. one minimal render is explicitly approved and completes;
6. output, logs, hashes, duration, actual cost, and cleanup are verified;
7. final specifications and change history are updated from observed results.
