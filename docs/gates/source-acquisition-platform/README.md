# P9-A Source Acquisition Platform Engineering Gate

Evidence date: 2026-08-24 (Asia/Shanghai).

Implementation: `IMPLEMENTED`

Engineering Gate: `CLOSED`

Release Qualification: `NOT_STARTED`

Contract maturity: `IMPLEMENTED` (not `STABLE`)

## Outcome

P9-A extends the deterministic Phase 8 internal pipeline with a reusable acquisition control plane:
policy-bound Fetch contracts, immutable RawArtifact provenance, semantic content validation,
versioned Source Recipes, bounded orchestration, VALID-only Document advancement, offline replay,
semantic health/drift evidence and measured integration cost.

The two P1 findings from the first independent acceptance were repaired and the isolated repair
verifier completed with exit code `0`, satisfying the Engineering Gate checks. A new independent
read-only acceptance has been requested for the repair candidate. This does not mean every official
site is currently accessible. Challenge, zero-discovery, parse failure and disallowed redirect
outcomes are explicit health evidence rather than silent success.

## Boundaries

- No CAPTCHA, login, paywall, cookie-challenge, signature or access-control bypass exists.
- No source-specific transport, retry, persistence, validation, replay, health or evidence storage
  exists.
- No BrowserFetcher, scheduler, Redis queue, distributed workflow or live-network CI exists.
- No source adapter changes Opportunity or Eligibility schema or bypasses the established
  RawArtifact -> Document -> Opportunity path.
- Real response bodies are not committed to Git; default tests are network-free.
- The 100-source/14-day no-daily-maintenance target is `NOT_RUN`.
- There was no push, merge, deployment or work beyond A7.

## Evidence index

- [A5 feasibility](a5-feasibility.md)
- [A6 S02 acceptance](a6-s02-acceptance.md)
- [A7 multi-source evidence](a7-multi-source-evidence.md)
- [Acceptance results](acceptance-results.md)
- [Test summary](test-summary.md)
- [Health and integration cost](health-and-cost.md)
- [Security and compliance](security-and-compliance.md)
- [Code review](code-review.md)
- [Deferred decisions](deferred-decisions.md)
