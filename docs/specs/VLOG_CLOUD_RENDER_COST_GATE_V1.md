# Vlog Cloud Render Cost Gate v1

Status: LOCAL PREFLIGHT VERIFIED / PAID CLOUD TEST PENDING

## Decision

Oracle remains the interactive UI, project store, and review surface. Heavy FFmpeg rendering is prepared as a one-shot Cloud Run Job using Cloud Storage for explicit input/output exchange and Artifact Registry for the reviewed container image.

This does not authorize automatic publishing, unattended recurring execution, or background media processing. Every potentially paid operation requires a fresh human approval.

## Non-negotiable invariant

No operation with a realistic possibility of charge may execute before all of the following are shown and explicitly approved:

1. current Security Pass status and fingerprint
2. successful local file existence, size, and SHA-256 revalidation
3. target project, region, bucket, and job
4. input size
5. CPU, memory, timeout, and task count
6. estimated maximum charge in yen
7. single-use approval identifier
8. expiry time

A UI click alone is not approval. Reuse, retry, parallel execution, silent fallback, and automatic resubmission are prohibited by default.

## Fixed initial limits

- project: `rts-vlog-render`
- region: `asia-northeast1`
- bucket: `rts-vlog-render-files-20260805`
- job: `rts-vlog-render`
- task count: `1`
- CPU: `1` or `2`
- memory: maximum `4 GiB`
- timeout: maximum `900 seconds`
- input: maximum `512 MiB`
- paid test approvals: maximum `3 per UTC day`
- approval lifetime: `15 minutes`
- Security Pass maximum age: `60 minutes`
- automatic retry: disabled

## Components

### `scripts/media_security_gate.py`

Free local inspection that validates media type, name, size, stream structure, resolution, frame rate, and duration. It issues a policy-bound `SECURITY_PASS` containing the exact local path, size, and SHA-256 for each accepted source.

### `scripts/cloud_cost_gate.py`

Free local preflight. It validates fixed cloud boundaries and the current Security Pass, then reopens every listed local source and verifies that it still exists, is not a symlink, and still matches both the inspected size and SHA-256.

It prints the security result and full estimate, requires `--approve`, and then requires the operator to type `YES`. Only then does it create a short-lived single-use approval record. It does not call Google Cloud and does not itself incur cloud execution charges.

### `cloud_render/worker.py`

One-shot worker intended for Cloud Run Jobs. It requires both `RENDER_MANIFEST_URI` and `COST_APPROVAL_ID`, rejects approval mismatches and task counts other than one, downloads reviewed inputs, revalidates the GCS boundary and every input hash, runs bounded FFmpeg processing, and uploads one new output object.

### `cloud_render/Dockerfile`

Reviewed container boundary containing Python, FFmpeg, and the Cloud Storage client only.

## Required flow

```text
Security Gate
→ local source hash revalidation
→ estimate display
→ explicit one-shot approval
→ isolated upload
→ execute exactly one Cloud Run Job
→ inspect output and Cloud logs
→ inspect approval consumption, cleanup, and actual billing data
→ separately approve any next action
```

## Local verification completed

The free path has been verified on Oracle using synthetic media and reject cases.

- valid Security Pass generation
- unsafe filename rejection
- unsupported suffix rejection
- malformed media rejection
- expired, policy-mismatched, and byte-mismatched Security Pass rejection
- missing-file rejection
- symlink rejection
- changed-size rejection
- same-size changed-content rejection by SHA-256
- real local preflight output included `local_hash_revalidated: true`
- preflight stopped at the approval boundary without `--approve`
- combined result: `14 passed`

## Remaining test order

1. Show the exact secured image tag, build command, and estimated maximum charge.
2. Obtain explicit approval for one Cloud Build.
3. Build and inspect the secured image.
4. Update the Cloud Run Job image without executing it.
5. Prepare one isolated synthetic input and manifest.
6. Show the first render estimate and receive a separate explicit approval.
7. Execute the minimal synthetic-media test once.
8. Inspect output, logs, hashes, runtime, storage use, approval consumption, duplicate-use refusal, cleanup, and billing.
9. Update all architecture, operation, deployment, rollback, cost, security, and test documents from the observed working configuration.

Approval for the image build does not authorize the render. Updating the Job image does not authorize executing the Job.

## Prohibited

- embedding credentials or private links
- recurring schedules
- automatic retries
- concurrent render tasks
- execution from page load or ordinary save actions
- automatic upload or publishing
- bypassing approval because an estimate is small or a free credit exists
- treating the old `cost-gated-v1` image as the secured image
- using real, private, customer, or copyrighted media before synthetic end-to-end validation succeeds
