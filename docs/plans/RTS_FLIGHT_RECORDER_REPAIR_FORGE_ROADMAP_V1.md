# RTS Flight Recorder / Repair Forge v1 — Implementation Roadmap

## Progress convention

`current / total` means the current item number from the top divided by the total number of items in the relevant phase.

Current overall position: **4 / 34**. Contract tests are authored and await execution on the Oracle test host.

## Phase 1 — Specification and adversarial review (1–6)

1. Draft architecture specification. **DONE**
2. Draft Devil's Advocate Gate specification. **DONE**
3. Define canonical JSON schemas. **DONE**
4. Write contract tests for schemas and illegal transitions. **AUTHORED — EXECUTION PENDING**
5. Run Devil's Advocate Gate A and B. **PROVISIONAL PASS_WITH_CONDITIONS**
6. Revise and freeze v1 contracts.

Exit: frozen schemas and all contract tests passing.

## Phase 2 — Flight Recorder minimal runtime (7–13)

7. Implement session lifecycle and identifiers.
8. Implement append-only event envelope.
9. Capture navigation, activation, API outcome, JS errors, and connectivity.
10. Add redaction and allowlist layer.
11. Add offline queue, deduplication, ordering, and retry.
12. Add user-visible recording state and manual report finalization.
13. Run Devil's Advocate Gate C against recorder failure modes.

Exit: product workflow remains usable when recording fails, while repair claims are blocked when evidence is incomplete.

## Phase 3 — Incident normalization and Debug Engine handoff (14–18)

14. Implement incident report finalizer.
15. Build expected-vs-observed path comparator.
16. Identify first divergence and evidence gaps.
17. Generate reproduction/test candidates.
18. Run adversarial malformed, partial, duplicated, and cross-session report tests.

Exit: one real Vlog session produces a redacted, reproducible incident package.

## Phase 4 — Repair Forge bounded prototype (19–26)

19. Define repair-plan allowlist and patch limits.
20. Generate a failing reproduction test before patching.
21. Refuse non-reproducible incidents by default.
22. Generate minimal patch on a dedicated repair branch.
23. Run targeted and full regression tests.
24. Generate patch-review and rollback bundle.
25. Run Devil's Advocate Gate D.
26. Require human approval; do not deploy automatically.

Exit: repair candidate demonstrates FAIL-before / PASS-after without weakening controls.

## Phase 5 — End-to-end Vlog trial (27–31)

27. Record one deliberately induced Vlog defect.
28. Diagnose and create repair plan.
29. Generate and validate patch.
30. Replay the identical operation sequence.
31. Store VERIFIED or REGRESSION_FOUND result.

Exit: complete evidence chain from operation to verified replay.

## Phase 6 — Formal candidate and release (32–34)

32. Run Devil's Advocate Gate E and performance/redaction audit.
33. Produce formal candidate, migration, and rollback instructions.
34. Human approval and merge to the formal target branch.

## Release blockers

- schema ambiguity
- incomplete or unredacted evidence
- recorder interferes with normal operation
- reproduction does not fail before patch
- test weakening or guard bypass
- patch exceeds approved scope
- unresolved regression
- missing rollback
- no human approval
