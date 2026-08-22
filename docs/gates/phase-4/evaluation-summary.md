# Phase 4 Synthetic Evaluation Summary

## Evidence state

- Implementation: `IMPLEMENTED`; deterministic fixture loader, runner, protected-negative stop
  and immutable run rows exist.
- Engineering Gate: `OPEN` pending exact-SHA remote CI.
- Release Qualification: `NOT_STARTED`.
- Contract Maturity: `IMPLEMENTED` (not `STABLE`).
- Locally verified: 12/12 fixed Golden statuses reproduced through the real eligibility engine.
- remote CI: pending.
- Synthetic evaluation: `SYNTHETIC_EVALUATION_ONLY`; manifest SHA-256
  `5b9f5ba97c5f236e7fdf618760cca9871dcc27782a4f2f6e8be7b5ac35932272`.

## Fixed result

| Integer measure | Result |
|---|---:|
| Golden cases | 12 |
| Expected statuses reproduced | 12 |
| Expected `INELIGIBLE` | 3 |
| Actual `INELIGIBLE` | 3 |
| Unexpected `INELIGIBLE` | 0 |
| Replay mismatches | 0 |
| Mother profiles | 20 |
| Versioned derived profiles | 100 |

The result covers controlled boundary, missing, conflict, professional mapping, education,
graduation, region, certificate and false-negative-protection cases. It cannot be converted into
production accuracy, trust, retention, willingness-to-pay or proof of the planned `<=0.5%`
false-negative threshold.

Because no governed real annotated evaluation or real-user qualification has started, this result
does not advance Release Qualification or Contract Maturity beyond `IMPLEMENTED`.
