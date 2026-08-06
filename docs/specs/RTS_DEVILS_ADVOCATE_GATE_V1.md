# RTS Devil's Advocate Gate v1

Status: ACTIVE REVIEW CONTRACT

## 1. Role

The Devil's Advocate Gate is an adversarial review stage. It does not implement features. It attempts to disprove that a specification, diagnosis, test, or repair patch is safe and sufficient.

A gate result is one of:

- `PASS`
- `PASS_WITH_CONDITIONS`
- `REVISE`
- `REJECT`

Silence or missing evidence is never PASS.

## 2. Gate positions

### Gate A — Specification challenge

Runs before implementation.

Questions:

- Can the recorder itself break or materially slow the user workflow?
- Can missing events create a false diagnosis?
- Can sensitive data leak through payloads, URLs, errors, or DOM text?
- Can a session be confused with another request or execution?
- Can offline delivery reorder or duplicate events?
- Can the repair system modify the wrong repository, branch, project, or incident?
- What happens when the recorder endpoint is unavailable?
- Is disabling recording fail-open for product operation and fail-closed for repair claims?

### Gate B — Contract and test challenge

Runs after schemas/tests are written and before implementation is accepted.

Questions:

- Does every normative requirement have a test or explicit human check?
- Can the test pass without the real behavior occurring?
- Are timestamps, ordering, retries, duplicates, and partial sessions covered?
- Can test fixtures accidentally contain secrets?
- Are negative and malformed inputs covered?

### Gate C — Implementation challenge

Runs after implementation and before formal candidate status.

Required attacks:

- rapid repeated taps
- navigation during pending requests
- background/foreground transitions
- network loss and recovery
- stale request IDs and replayed events
- duplicate and out-of-order events
- storage full or unwritable
- recorder API 4xx/5xx/timeout
- unsupported browser APIs
- malformed report ingestion

### Gate D — Repair patch challenge

Runs for every generated patch.

Reject when any condition is true:

- reproduction test did not fail before patch
- patch changes expected result instead of fixing behavior
- errors are swallowed or converted to success
- tests are deleted, skipped, or weakened
- security, approval, cost, or governance paths are bypassed
- change scope exceeds repair plan
- unrelated refactor obscures the fix
- rollback is unavailable
- regression suite is incomplete or failing

### Gate E — Formal release challenge

Runs before merge to the formal branch.

Evidence required:

- complete artifact chain
- redaction audit
- successful replay on the original scenario
- at least one recovery scenario
- no material performance regression
- human approval identity and timestamp
- rollback rehearsal

## 3. Required gate report

Each gate emits:

```json
{
  "gate": "A|B|C|D|E",
  "decision": "PASS|PASS_WITH_CONDITIONS|REVISE|REJECT",
  "claims_challenged": [],
  "counterexamples": [],
  "missing_evidence": [],
  "required_changes": [],
  "residual_risks": [],
  "reviewed_artifacts": [],
  "reviewed_at": "RFC3339"
}
```

## 4. Non-negotiable principle

The Devil's Advocate Gate must be organizationally and logically separate from the agent that generated the specification or patch. Self-review may supplement but cannot replace adversarial review.