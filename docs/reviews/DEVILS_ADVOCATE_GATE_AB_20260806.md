# Devil's Advocate Gate A/B Review

Decision: `PASS_WITH_CONDITIONS`

This provisional review does not replace the independent reviewer required by the gate specification.

## Counterexamples found

- Valid events can still be mixed across sessions.
- JSON Schema cannot enforce contiguous ordering or `current <= total` by itself.
- Sensitive values can hide under generic keys or inside error text.
- A diagnosis can claim high confidence despite missing evidence.
- A structurally valid replay can differ semantically from the expected path.
- Patch scope and limits require cross-artifact comparison.
- Validator-specific regular expressions reduce portability.

## Corrections completed

- Replaced a validator-specific payload-key expression with an explicit forbidden-key contract.
- Added semantic tests for mixed sessions, broken ordering, and impossible progress.
- Added tests rejecting repair without a failing pre-patch reproduction.
- Added tests rejecting weakened tests, hidden errors, and guard bypasses.
- Added replay and evidence-confidence contradiction tests.

## Conditions before freeze

1. Run the contract suite on the Oracle test host.
2. Add a production semantic validator for cross-record rules.
3. Add recursive value and URL redaction.
4. Add cross-artifact ID, scope, and limit checks.
5. Obtain an independent adversarial review.

Reviewed at: `2026-08-06T20:44:00+09:00`
