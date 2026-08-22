# Phase 8 Security And Compliance Review

This is an engineering review, not legal advice, production-identity approval or public-release
qualification.

## Identity, authorization and privacy

- Preference and inbox endpoints derive the owner from the server-side principal; no request body
  or path `user_id` is authoritative.
- Fixture authentication is disabled by default outside development/test. The browser credential is
  a fixed synthetic test token, not a production secret or real identity.
- Other-owner and unknown private reads do not disclose reminder existence. Responses omit session
  digests, unrelated profile fields and internal lease/error details.
- Reminder consent is independent from saving an opportunity. Missing preference means disabled;
  current disable, unsave or purpose revocation suppresses a pending candidate.

## Integrity and failure safety

- Candidate insertion shares the OpportunityVersion/Event transaction; rollback prevents partial
  candidates.
- Immutable Outbox intent fields are trigger-protected. Composite foreign keys bind action,
  preference and UserState snapshots to the same owner.
- Before delivery, the worker revalidates governed public version, event/version/evidence facts,
  exact event-time latest audience snapshots and current user controls.
- Lease tokens prevent stale workers from completing another worker's claim. Adapter errors use
  stable redacted codes and bounded attempt accounting; logs do not include bearer tokens.
- Test-inbox replay compares the complete persisted delivery contract and cannot silently accept a
  mismatched duplicate.

## Data, dependency and scope review

- Fixture license is `CC0-1.0 synthetic fixture`; the manifest declares no personal data or
  business truth and validates its SHA-256.
- Runtime database/object-store credentials are disposable test constants. No production provider
  credential, `.env`, browser state, trace, screenshot, video, local database or build directory is
  tracked.
- The only new Web test dependency is exact `@playwright/test@1.62.1`; it is locked and used only for
  the isolated Chromium engineering journey.
- No real external message provider, arbitrary URL intake, production session lifecycle, marketing
  tracking or notification analytics is present.

Production identity, privacy access/export/deletion, retention, provider data processing,
rate-limits, incident response, current legal review and human-participant authorization remain
Release Qualification/deployment blockers.
