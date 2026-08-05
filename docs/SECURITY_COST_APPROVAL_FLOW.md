# Vlog Emergency Overflow: Security → Cost → Approval Flow

Status: LOCAL FLOW VERIFIED / PAID CLOUD EXECUTION NOT YET REVALIDATED

## Position

Oracle remains the normal UI, storage-control, editing, and lightweight processing environment.

Google Cloud is not the default renderer. It is a manually selected emergency overflow path used only when the normal Oracle environment cannot finish a heavy render without destabilizing the service.

## Required sequence

```text
LOCAL MEDIA
→ scripts/media_security_gate.py
→ SECURITY_PASS.json (hash-bound)
→ scripts/cloud_cost_gate.py
→ local file existence / size / SHA-256 revalidation
→ estimate and consequence display
→ explicit one-shot approval record
→ upload to isolated GCS prefixes
→ Cloud Run Job
→ worker re-verifies URI boundary, hashes, and stream structure
→ FFmpeg render
→ new output object only
→ outcome, approval-consumption, cleanup, and cost review
```

The Cloud Run Job must not run before both gates pass and a fresh human approval is issued.

## Security Gate

`scripts/media_security_gate.py`:

- accepts allowlisted media suffixes only
- rejects symlinks and unsafe filenames
- limits each file to 512 MiB
- runs `ffprobe` with a 30-second timeout
- rejects attachment, data, subtitle, and unknown streams
- requires exactly one video/image stream
- limits resolution, frame rate, duration, and stream count
- records SHA-256 for every accepted file
- produces a `SECURITY_PASS` with policy ID and fingerprint
- fails closed on unknown, timeout, invalid structure, or probe failure

Files should be renamed to generated internal ASCII identifiers before inspection.

## Cost Gate

`scripts/cloud_cost_gate.py` refuses to estimate or approve without a current `SECURITY_PASS`.

Before displaying an approval candidate it now reopens every local source file and verifies:

- the path is present in the Security Pass
- the source still exists as a regular file
- the source is not a symlink
- the current byte size matches the inspected size
- the current SHA-256 matches the inspected SHA-256

This blocks deletion, path substitution, size changes, and same-size content replacement between inspection and cost approval.

Approval records include:

- Security Gate policy and fingerprint
- exact input hashes
- Google project, region, bucket, and job
- CPU, memory, timeout, task count, and estimated ceiling
- expiry and single-use marker

Defaults are one CPU, 1 GiB memory, one task, no automatic retry, and ten-minute timeout.

## Storage boundary

The worker accepts only:

- bucket: `rts-vlog-render-files-20260805`
- manifests: `manifests/`
- inputs: `inputs/`
- outputs: `outputs/`

It rejects other buckets, prefixes, path traversal, unsupported suffixes, active/attachment/data streams, missing hashes, and hash mismatch.

Output upload uses an object-generation precondition so an existing object is not silently overwritten.

## Cloud worker

The worker downloads the approved manifest and inputs, recomputes every SHA-256, probes the downloaded content again, and only then invokes FFmpeg.

FFmpeg runs with:

- no stdin
- one thread
- bounded process timeout
- metadata and chapters removed
- no shell command interpolation

The worker image must be rebuilt after security changes. The currently deployed `cost-gated-v1` image predates this Security Gate and must not be executed for production or untrusted inputs.

## Verified local evidence

Oracle validation completed with synthetic media and reject cases:

- valid one-second MP4 accepted and Security Pass issued
- unsafe filename rejected
- allowlist violation rejected
- malformed MP4 rejected
- size-mismatched pass rejected
- expired pass rejected
- unsupported policy rejected
- missing local source rejected
- symlink source rejected
- changed-size source rejected
- same-size changed-content source rejected by SHA-256
- fresh end-to-end local preflight reported `local_hash_revalidated: true`
- the process stopped at `approval required` without issuing approval
- combined test result: `14 passed`

These checks were local and did not execute Cloud Build, Cloud Run, or a paid render.

## Remaining approved actions

The remaining work is intentionally split into separate paid-capable decisions:

1. show the build target, image tag, and estimated maximum charge;
2. obtain explicit approval for one secured container build;
3. build and inspect the new image;
4. update the Cloud Run Job image without executing it;
5. prepare isolated synthetic GCS input and manifest;
6. show the render estimate and obtain a separate one-shot approval;
7. execute one minimal render;
8. verify output hash, logs, duration, actual cost, approval consumption, duplicate-use refusal, and cleanup;
9. update final specifications and history from the observed cloud result.

Build approval does not authorize render execution. Job-image update does not authorize Job execution. Every paid-capable action remains fail-closed and separately approved.
