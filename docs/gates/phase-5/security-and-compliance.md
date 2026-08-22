# Phase 5 Security And Compliance Review

Status: implemented and locally verified; remote CI pending. This is engineering review, not legal
advice or production authorization.

## Read-only and data-minimization controls

- The public router defines GET only; no public POST/PUT/PATCH/DELETE route exists.
- Each public DB dependency executes `SET TRANSACTION READ ONLY`, rolls back and closes.
- Integration evidence confirms PostgreSQL rejects a write through that transaction.
- Public schemas exclude storage bucket/object keys, parser URIs, review actor, profile, rule,
  eligibility, model confidence and personalized rank fields.
- Problem responses are stable `application/problem+json` and do not expose SQL/query/connection
  details.

## Publication and evidence controls

- A row must be in the version-bound public allowlist, match the current published Opportunity and
  a non-rejected v0.3 version, and pass public-field completeness checks.
- Every projected field must have an official-source EvidenceRef. Field evidence below precedence
  300 is rejected, so LLM semantic inference and human-only mapping cannot become public hard fact.
- Official links reject embedded URL credentials. Evidence locator identity and change history are
  preserved without copying source bodies into the public response.
- Public use basis is constrained to open license, official public access or link-only treatment.

## License, privacy, secret and artifact scan

- Fixture manifest declares CC0 synthetic content, no personal data, no business truth and no
  Release Qualification eligibility; SHA-256 matches exact fixture bytes.
- The three records use reserved `.example.test` hosts and contain no licensed original document.
- Diff scans found only explicit disposable test credentials in compose/CI/test URL rendering;
  there is no external token, cookie, private key, production credential or `.env` file.
- No database, object, cache, `node_modules`, `.next`, Playwright state, screenshot, trace, log or
  generated agent file is tracked.
- The raw watermarked `设计/logo.png` is not copied into Web output. The UI uses the approved name,
  casing and tagline as text and does not invent a replacement logo.

## Isolation

Phase 5 commands accepted only `deepaha-phase5-*`, `infra/compose.phase5.yaml`, PostgreSQL 55435 and
Moto 55003. Local verification removed only its exact projects. Existing upstream worktrees,
branches and live observation were not changed, stopped or used as test dependencies.

## Remaining release review

Before Release Qualification, real candidate data needs documented permission/use basis, privacy
review, official-link and evidence replay, public AI-content marking review as applicable, and legal
confirmation for the actual operator/features/region. None is claimed here.
