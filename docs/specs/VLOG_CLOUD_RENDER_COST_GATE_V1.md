# Vlog Cloud Render Cost Gate v1

Status: IMPLEMENTED / NOT YET PAID-TESTED

## Decision

Oracle remains the interactive UI, project store, and review surface. Heavy FFmpeg rendering is prepared as a one-shot Cloud Run Job using Cloud Storage for explicit input/output exchange and Artifact Registry for the reviewed container image.

This does not authorize automatic publishing, unattended recurring execution, or background media processing. Every potentially paid operation requires a fresh human approval.

## Non-negotiable invariant

No operation with a realistic possibility of charge may execute before all of the following are shown and explicitly approved:

1. target project, region, bucket, and job
2. input size
3. CPU, memory, timeout, and task count
4. estimated maximum charge in yen
5. single-use approval identifier
6. expiry time

A UI click alone is not approval. Reuse, retry, parallel execution, silent fallback, and automatic resubmission are prohibited by default.

## Fixed initial limits

- project: `rts-vlog-render`
- region: `asia-northeast1`
- bucket: `rts-vlog-render-files-20260805`
- task count: `1`
- CPU: `1` or `2`
- memory: maximum `4 GiB`
- timeout: maximum `900 seconds`
- input: maximum `512 MiB`
- paid test approvals: maximum `3 per UTC day`
- approval lifetime: `15 minutes`
- automatic retry: disabled

## Components

### `scripts/cloud_cost_gate.py`

Free local preflight. It validates fixed boundaries, prints the full estimate, requires `--approve`, then requires the operator to type `YES`. It creates a short-lived single-use approval record. It does not call Google Cloud and does not itself incur cloud execution charges.

### `cloud_render/worker.py`

One-shot worker intended for Cloud Run Jobs. It requires both `RENDER_MANIFEST_URI` and `COST_APPROVAL_ID`, rejects approval mismatches and task counts other than one, downloads reviewed inputs, runs bounded FFmpeg concatenation, and uploads one output object.

### `cloud_render/Dockerfile`

Reviewed container boundary containing Python, FFmpeg, and the Cloud Storage client only.

## Required flow

```text
free local validation
-> estimate display
-> explicit one-shot approval
-> upload reviewed manifest and inputs
-> execute exactly one Cloud Run Job
-> inspect output and Cloud logs
-> inspect actual billing data
-> separately approve any next test
```

## Test order

1. Unit-test the free cost gate.
2. Build the container only after showing that Cloud Build may incur cost and receiving approval.
3. Create the Cloud Run Job configuration without executing it.
4. Show the first-run estimate and receive explicit approval.
5. Execute a minimal synthetic-media test once.
6. Inspect output, logs, runtime, storage use, and billing.
7. Update all architecture, operation, deployment, rollback, cost, security, and test documents based on the observed working configuration.
8. Only then continue normal feature development.

## Prohibited

- embedding credentials or private links
- recurring schedules
- automatic retries
- concurrent render tasks
- execution from page load or ordinary save actions
- automatic upload or publishing
- bypassing approval because an estimate is small or a free credit exists
