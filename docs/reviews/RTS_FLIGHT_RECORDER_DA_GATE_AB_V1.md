# RTS Flight Recorder / Repair Forge v1 — Devil's Advocate Gate A/B

## Decision

**PASS_WITH_CONDITIONS**

The canonical schemas and contract tests are sufficient to begin the bounded Flight Recorder runtime, but the contracts are not considered frozen until the conditions below are implemented and retested.

## Evidence

- Six canonical JSON Schema documents exist for the evidence chain.
- Contract tests reject cross-session mixing, duplicate or reversed sequence numbers, illegal progress values, secret-bearing keys, unsupported lifecycle jumps, reproduction-free repair plans, test weakening, guard bypass, and false VERIFIED replay results.
- Oracle execution on 2026-08-06: **27 passed**.

## Conditions

1. Runtime event construction must apply recursive redaction before persistence or transmission.
2. Recorder failures must never block the product workflow.
3. Session identifiers and event identifiers must be generated locally and remain opaque.
4. Events must be append-only and sequence numbers must be monotonic inside one session.
5. A bounded in-memory queue must prevent unbounded growth.
6. Evidence gaps must be represented explicitly; they must not be silently converted into successful diagnosis.
7. Recording must default to metadata only. Free text, media bytes, authorization data, cookies, and URL secrets are forbidden.

## Gate B adversarial findings

The following cannot be guaranteed by JSON Schema alone and therefore require semantic validators or runtime tests:

- ordering across multiple events
- uniqueness across multiple events
- cross-artifact session consistency
- FAIL-before / PASS-after truthfulness
- recorder non-interference with the user workflow
- recursive secret removal from nested values

## Exit rule

Gate A/B becomes **PASS** only after the minimal runtime and its tests demonstrate conditions 1–5, without weakening the existing contract suite.
