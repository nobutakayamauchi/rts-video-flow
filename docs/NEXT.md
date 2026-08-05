# rts-video-flow Next Actions

The next goal is to validate the Security → Cost → Approval path before any further paid or cloud execution.

## Required order

1. Pull the latest `feat/narration-segments-v1` branch on Oracle.
2. Run all free local unit tests.
3. Generate a tiny safe media sample locally.
4. Generate deliberately rejected samples without using customer or private media.
5. Verify `scripts/media_security_gate.py` produces a hash-bound SECURITY_PASS only for the safe sample.
6. Verify unsafe filenames, unsupported types, extra streams, limits, timeouts, and hash replacement fail closed.
7. Verify `scripts/cloud_cost_gate.py` refuses missing, expired, changed, and size-mismatched passes.
8. Review all changed specifications and tests.
9. Before Cloud Build, display the exact build target, execution count, timeout, automatic retry setting, and monetary ceiling.
10. Obtain explicit one-shot approval.
11. Build and push the secured image once; do not automatically retry.
12. Verify the image exists.
13. Update the Cloud Run Job to the new image without executing it.
14. Prepare the smallest test manifest and isolated GCS objects.
15. Recalculate the render ceiling and consequences.
16. Obtain a separate explicit one-shot approval for the Cloud Run execution.
17. Execute once.
18. Verify output object, input/output hashes, logs, duration, actual cost, and cleanup.
19. Mark the approval consumed and verify duplicate execution is rejected.
20. Update README, STATUS, architecture, operating procedure, troubleshooting, and change history from observed results.

## Free local validation command

```bash
python3 -m pytest -q tests/test_cloud_cost_gate.py tests/test_media_security_gate.py
```

This command must not call Cloud Build, Cloud Run, GCS transfer, or another paid external service.

## Stop conditions

Stop and report instead of continuing if:

- any Security Gate test fails
- the Security Pass can be reused after the input changes
- Cost Gate can run without a current Security Pass
- a changed hash can reach the worker
- a bucket or prefix outside the allowlist is accepted
- a paid action appears without a current explicit approval
- automatic retry, parallelism above one, or automatic fallback is enabled
- the monetary ceiling cannot be stated with adequate confidence
- secrets or real/private media would be required

## Do not do yet

Do not:

- execute the current `cost-gated-v1` Job image
- upload real user media
- create recurring Jobs or schedules
- enable automatic retry
- broaden Storage permissions
- add public bucket access
- add automatic publication or upload
- claim the secured overflow renderer is complete

## Documentation propagation after success

After the real secured execution succeeds, update and reconcile:

- `README.md`
- `AGENTS.md`
- `docs/STATUS.md`
- `docs/NEXT.md`
- `docs/VLOG_MVP_SPEC.md`
- `docs/SECURITY_COST_APPROVAL_FLOW.md`
- deployment and troubleshooting docs
- the limit-development public documentation
- RTS decision/boundary records or proposals

Old Oracle-only assumptions should be replaced where false. Historical incident details should move to decision/change history rather than remain as active instructions.
