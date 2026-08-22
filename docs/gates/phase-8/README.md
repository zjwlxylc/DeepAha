# Phase 8 Engineering Gate

Evidence date: 2026-08-23 (Asia/Shanghai).

Implementation: `IMPLEMENTED`

Engineering Gate: `OPEN`

Release Qualification: `NOT_STARTED`

v0.7 Contract Maturity: `IMPLEMENTED` (not `STABLE`)

## Candidate conclusion

Implementation candidate `6586f4b784afb05b0a5070d07a379dc663372e92` implements one bounded
Phase 8 variable: a governed `DEADLINE_CHANGED` event for
`application_window.closes_on`, bound to exact OpportunityVersion, OpportunityEvent, EvidenceRef,
saved action, independent reminder preference and UserState snapshots. The only delivery target is
the local PostgreSQL `TEST_INBOX` adapter.

Fresh local verification, migration round trip, PostgreSQL integration, real Chromium smoke and an
independent review have passed. GitHub Actions run
[`32586782360`](https://github.com/zjwlxylc/DeepAha/actions/runs/32586782360) is successful on the
implementation candidate with all nine required jobs. The Engineering Gate remains `OPEN` until
the exact Gate-package commit also completes all nine jobs successfully.

## Evidence boundary

- The fixture is CC0, fixed, synthetic and Release Qualification-ineligible.
- Delivery target: `TEST_INBOX`; real notification providers and channels: `0`.
- Real participants: `0`; human track and Release Qualification: `NOT_STARTED`.
- The only valid human/release conclusion remains `HOLD_MISSING_HUMAN_EVIDENCE`.
- Engineering delivery, retry and browser pass counts are not open rate, complaint rate,
  retention, action or product-value metrics.
- Phase 6 and Phase 7 Release Qualification remain independent `NOT_STARTED` axes. They do not
  block Phase 8 engineering review, and Phase 8 evidence does not qualify their human or production
  conclusions.

## Implemented boundary

- Additive v0.7 reminder preference, immutable intent, delivery-attempt and test-inbox contracts.
- Atomic candidate capture with the opportunity event; exact event-time latest-snapshot audience.
- Transactional Outbox, lease recovery, bounded retries, stable suppression/failure codes and
  complete idempotent replay checks.
- Owner-scoped preference/inbox API and a minimal responsive Web route with an explicit on/off
  control.
- Pre-delivery public-governance, current-control and event-time immutable-binding rechecks.

There is no real provider, push, mini-program, calendar, multi-channel orchestration, operations
console, production identity, commercialization, deployment, release or Phase 9 work.

## Evidence index

- [Acceptance results](acceptance-results.md)
- [Test summary](test-summary.md)
- [Browser verification](browser-verification.md)
- [Security and compliance](security-and-compliance.md)
- [Operations](operations.md)
- [Deferred decisions](deferred-decisions.md)
- [Engineering metrics](engineering-metrics.md)
