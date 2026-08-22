# Phase 4 Deferred Decisions

## Evidence state

- Implementation: `IMPLEMENTED` for the bounded deterministic Phase 4 scope only.
- Engineering Gate: `CLOSED`.
- Release Qualification: `NOT_STARTED`.
- Contract Maturity: `IMPLEMENTED` (not `STABLE`).
- Locally verified: synthetic and local technical checks only.
- remote CI: exact candidate passed all five required jobs in
  [run 32543551989](https://github.com/zjwlxylc/DeepAha/actions/runs/32543551989).
- Synthetic evaluation: useful for coverage and replay, not real-world validation.

## Deferred

- Governed real annotated evaluation and proof of the planned `INELIGIBLE` false-negative
  threshold `<=0.5%`.
- LLM/Model Gateway, semantic inference execution and any prompt-governed workflow.
- Phase 5 public opportunity index and UI.
- Phase 6 real profile collection, ranking, personal actions and API/UI flows.
- Live users, trust, comprehension, retention, willingness-to-pay and commercial evidence.
- Redis/Valkey/Celery, pgvector, OCR, notifications, feedback and production cloud.
- Release Qualification, contract promotion to `STABLE`, merge, release and publication.

These items require their own authority, spec and evidence. Phase 4 Engineering Gate closure does
not imply that any deferred item has started or qualified.
