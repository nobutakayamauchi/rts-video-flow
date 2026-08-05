# rts-video-flow Status

Status: ACTIVE NARROW IMPLEMENTATION / LOCAL SECURITY PATH VERIFIED / PAID CLOUD REVALIDATION PENDING

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
→ Local hash revalidation
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

## Security controls represented in code

- allowlisted media suffixes
- regular-file and non-symlink requirement
- safe internal ASCII filename requirement
- 512 MiB per-file limit
- ffprobe timeout
- stream-type and stream-count limits
- resolution, duration, and frame-rate limits
- SHA-256-bound `SECURITY_PASS`
- Security Pass expiry, policy, and byte-count validation
- Cost Gate local file existence and non-symlink revalidation
- Cost Gate local size and SHA-256 revalidation
- refusal of same-size content replacement after inspection
- GCS bucket and prefix allowlist
- downloaded-input hash revalidation in the worker
- no shell interpolation
- FFmpeg stdin disabled
- one render thread
- render timeout
- metadata and chapters removed
- existing output object overwrite refusal

## Verified on Oracle

The free local path has been exercised with generated synthetic media and reject samples.

Verified results:

- a valid one-second MP4 produced a hash-bound `SECURITY_PASS`
- unsafe filename rejection
- non-allowlisted suffix rejection
- malformed MP4 rejection through ffprobe failure
- Security Pass input-size mismatch rejection
- expired Security Pass rejection
- unsupported policy rejection
- local source-file existence check
- local symlink rejection
- local size-change rejection
- local same-size content replacement rejection through SHA-256 mismatch
- a fresh real Security Pass reached the approval boundary with `local_hash_revalidated: true`
- execution stopped without `--approve`
- `14 passed` for the combined Security Gate and Cost Gate test set

No Cloud Build or Cloud Run execution was performed during these checks.

## Not yet verified

- new secured container image build
- Cloud Run Job image update
- end-to-end Security Pass → Cost Approval → GCS → Cloud Run → output flow
- approval consumption and duplicate-use refusal in a real cloud run
- actual runtime cost of the minimal secured render
- output hash, logs, duration, cleanup, and temporary-object lifecycle

## Prohibited until cloud revalidation

- executing the current Cloud Run Job with untrusted or real user media
- using the old `cost-gated-v1` image as the secured worker
- automatic paid fallback
- automatic retries
- recurring schedules
- public upload or publishing
- customer/private/copyrighted media
- claiming the secured cloud render is complete

## Completion condition

The emergency overflow path is complete only after:

1. a newly approved secured image build succeeds;
2. the Job is updated to the new image without execution;
3. one minimal synthetic render is separately and explicitly approved;
4. output, logs, hashes, duration, actual cost, approval consumption, and cleanup are verified;
5. final specifications and change history are updated from observed cloud results.

Until those steps are approved and observed, the local safety specification is verified while the paid cloud execution path remains pending.
