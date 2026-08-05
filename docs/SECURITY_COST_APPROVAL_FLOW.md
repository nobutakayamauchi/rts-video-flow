# Vlog Emergency Overflow: Security → Cost → Approval Flow

Status: IMPLEMENTED IN BRANCH / CLOUD EXECUTION NOT YET REVALIDATED

## Position

Oracle remains the normal UI, storage-control, editing, and lightweight processing environment.

Google Cloud is not the default renderer. It is a manually selected emergency overflow path used only when the normal Oracle environment cannot finish a heavy render without destabilizing the service.

## Required sequence

```text
LOCAL MEDIA
→ scripts/media_security_gate.py
→ SECURITY_PASS.json (hash-bound)
→ scripts/cloud_cost_gate.py
→ one-shot approval record
→ upload to isolated GCS prefixes
→ Cloud Run Job
→ worker re-verifies URI boundary, hashes, and stream structure
→ FFmpeg render
→ new output object only
→ outcome and cost review
```

The Cloud Run Job must not run before both gates pass.

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

`scripts/cloud_cost_gate.py` refuses to estimate or approve without a current `SECURITY_PASS` whose total bytes match the requested input size.

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

## Validation before next paid action

1. Pull the branch on Oracle.
2. Run local unit tests.
3. Run Security Gate against a tiny generated test video and a deliberately invalid file.
4. Review the resulting `SECURITY_PASS`.
5. Confirm Cost Gate refuses missing, expired, and size-mismatched passes.
6. Rebuild the container only after a new explicit cost approval.
7. Update the Cloud Run Job image without executing it.
8. Perform one explicitly approved minimal render.
9. Verify output hash, logs, duration, and actual cost.
10. Update final specifications and change history after the real execution succeeds.
