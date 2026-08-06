# RTS Flight Recorder / Debug Engine / Repair Forge v1

Status: DRAFT FOR DEVIL'S ADVOCATE REVIEW

## 1. Purpose

Create a closed loop for observing user operations, diagnosing failures, generating bounded repair patches, validating them, and feeding the result back into future diagnosis.

```text
User operation
→ RTS Flight Recorder
→ incident-report.json
→ RTS Debug Engine
→ repair-plan.json
→ RTS Repair Forge
→ reproduction test + bounded patch
→ regression validation
→ human approval
→ replay and feedback
```

## 2. Components

### 2.1 RTS Flight Recorder

Records system behavior, not private user content.

Required event classes:

- session lifecycle
- tap/click/submit
- navigation and visible screen state
- API start/success/failure
- JavaScript error and unhandled rejection
- connectivity loss/recovery
- request_id, execution_id, project, mode
- current step / total steps
- output existence and integrity metadata

Forbidden capture:

- cookies, authorization headers, tokens, passwords
- unrestricted form text
- media bytes or screenshots by default
- personal information not explicitly allowlisted
- full URLs containing secret query parameters

### 2.2 RTS Debug Engine

Consumes a completed incident report and produces:

- expected path vs observed path
- first divergence point
- failure class
- reproduction steps
- suspected files/components
- required regression tests
- confidence and missing evidence
- release-blocking decision

The engine must distinguish observation from inference.

### 2.3 RTS Repair Forge

Consumes the incident report and debug assessment. It must:

1. Generate a failing reproduction test first.
2. Refuse patch generation when the failure cannot be reproduced unless explicitly approved as an exploratory patch.
3. Generate a minimal patch on a dedicated branch.
4. Run the reproduction test and existing regression suite.
5. Reject patches that weaken tests, suppress errors, bypass security/cost approval, or alter success criteria merely to obtain PASS.
6. Produce a review bundle, never deploy automatically in v1.

## 3. State model

```text
IDLE
RECORDING
INCIDENT_DETECTED
REPORT_FINALIZED
DIAGNOSED
REPRODUCTION_READY
PATCH_CANDIDATE
VALIDATING
READY_FOR_HUMAN_REVIEW
APPROVED | REJECTED
REPLAYING
VERIFIED | REGRESSION_FOUND
```

Illegal transitions must be rejected and logged.

## 4. Canonical artifacts

- `flight-events.ndjson`: append-only raw events
- `incident-report.json`: redacted normalized incident
- `debug-assessment.json`: diagnosis and evidence map
- `repair-plan.json`: allowed scope and tests
- `patch-review.json`: diff metrics, test results, risks
- `replay-result.json`: post-patch observed result

## 5. Patch safety policy

V1 automatic patch generation may modify only allowlisted application and test paths. It may not automatically modify:

- authentication or authorization
- billing/cost gates
- secret handling
- deployment/IAM configuration
- destructive storage operations
- security policy
- governance approval logic

Hard limits, configurable per repository:

- maximum changed files
- maximum changed lines
- maximum new dependencies
- no test deletion
- no assertion weakening without explicit review
- no direct writes to main

## 6. Human approval

A patch is reviewable only when the bundle contains:

- incident summary
- evidence timeline
- failing reproduction test before patch
- passing reproduction test after patch
- full regression result
- changed files and line count
- unresolved risks
- rollback instructions

## 7. V1 acceptance criteria

The system is accepted when one Vlog defect can complete this loop:

```text
observe real operation
→ produce redacted incident report
→ identify first divergence
→ generate failing test
→ generate bounded patch
→ pass reproduction and regression tests
→ require human approval
→ replay the same scenario
→ store VERIFIED result
```

No claim of autonomous repair is permitted until this full loop is evidenced.