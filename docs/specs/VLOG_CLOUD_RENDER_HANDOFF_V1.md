# Vlog Cloud Render Handoff v1

## Purpose

Prevent Oracle-hosted Vlog rendering from exhausting memory while preserving a smartphone-first workflow. Heavy preview and final renders must leave the web process and run only through the governed RTS 3.5 overflow path.

## Confirmed failure

The previous synchronous `POST /api/output/render` implementation launched `process_vlog.sh` and `render_vlog.sh` inside `rts-video-flow-web.service`. On the 954 MiB Oracle host, a render child reached roughly 638 MiB RSS and was killed by the kernel OOM killer. The browser then appeared unresponsive because the HTTP request never completed normally.

## Safety invariants

1. The web service must never launch the heavy local render pipeline.
2. A render request must not execute paid cloud work without a separate explicit approval.
3. Media must pass the media security gate before cost approval is issued.
4. The cost approval must bind project, region, bucket, job, input hashes, security fingerprint, task count, timeout, resources, maximum yen, expiry, and single-use intent.
5. Submission must return quickly with a stable request identifier; the UI must not wait on the render process.
6. Reusing an approval ID, manifest, run ID, or output destination must be rejected.
7. Existing output must never be overwritten silently.
8. Preview and final output states must be auditable: `PREPARING`, `AWAITING_APPROVAL`, `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, or `REJECTED`.
9. Cloud execution is an emergency overflow path, not the normal default path.

## API contract

### Prepare

`POST /api/output/render/prepare`

Form fields:

- `project`: Vlog project name
- `mode`: `preview` or `final`

Behavior:

- validates project and required roles;
- inventories referenced media;
- runs the media security gate;
- creates a deterministic manifest candidate;
- calculates the bounded cloud configuration and cost estimate;
- creates a pending request record;
- performs no Cloud Run execution.

Response: HTTP `202`

```json
{
  "status": "AWAITING_APPROVAL",
  "request_id": "...",
  "project": "...",
  "mode": "preview",
  "estimated_max_yen": 3,
  "expires_at": 0,
  "security": {
    "status": "PASS",
    "fingerprint": "...",
    "files": 1
  }
}
```

### Approve and submit

`POST /api/output/render/approve`

Form fields:

- `request_id`
- `confirmation`: exact server-provided confirmation phrase

Behavior:

- revalidates pending request, expiry, security fingerprint, hashes, output destination, and non-consumption;
- issues or consumes the one-shot approval;
- uploads only approved inputs and manifest;
- starts exactly one Cloud Run Job execution;
- records the execution name;
- returns immediately without waiting for completion.

Response: HTTP `202`

```json
{
  "status": "QUEUED",
  "request_id": "...",
  "execution": "..."
}
```

### Status

`GET /api/output/render/status/{request_id}`

Returns the current governed state, timestamps, error summary, and completed download URL when available.

### Local legacy endpoint

`POST /api/output/render` must not launch local rendering. During migration it returns HTTP `503` with a clear message directing callers to the prepare/approve flow.

## UI flow

1. User taps preview or final.
2. UI calls `prepare` and shows security result plus maximum yen.
3. User explicitly approves one execution.
4. UI calls `approve`, receives `request_id`, and starts polling status.
5. UI remains usable and shows progress.
6. On completion, the final or preview link becomes available.
7. On failure, the UI shows a bounded error and recovery action; it never reloads to a blank page.

## Resource ceiling v1

- CPU: 1
- memory: 1 GiB
- tasks: 1
- parallelism: 1
- retries: 0
- timeout: 10 minutes
- maximum approved estimate: supplied by the server policy, initially 3 yen for the minimum validation path

## Delivery slices

1. Local-render hard stop and contract tests.
2. Persistent request-state model and prepare endpoint.
3. Explicit approval and single-use consumption.
4. Cloud Run submission adapter.
5. Status polling and output recovery.
6. Mobile UI integration.
7. End-to-end synthetic test, documentation, and RTS 3.5 completion review.
