# P9-A Security and Compliance Review

Evidence date: 2026-08-24.

Result: `PASS` for the bounded Engineering Gate; this is not legal approval or production
qualification.

## Enforced controls

- Fetch requests are bound to active Source/Endpoint/Recipe IDs, approved hosts, URL patterns,
  MIME expectations, timeout/retry/byte/request budgets and exact policy versions.
- Every redirect is re-resolved and rechecked against the public-host allowlist; credentials in
  URLs, private/non-global literal IPs and unapproved hosts fail closed.
- Content validation distinguishes HTTP success from usable content and stops on CAPTCHA, login,
  access-denied and JavaScript Cookie challenges.
- Only `VALID` evaluations may advance into Document. Raw bytes can remain immutable evidence but
  cannot become semantic truth after a challenge or validation failure.
- XML parsing disables network access and entity resolution. Replay object keys are relative,
  resolved under an explicit controlled root and protected against traversal.
- Live qualification requires two explicit opt-ins, accepts at most 25 requests, emits an
  allowlisted JSON summary and never prints bodies, cookies, credentials or unredacted headers.
- Current endpoint policies use a minimum interval of 21,600 seconds and record robots/use notes.
  Unavailable robots endpoints are not silently interpreted as permission.
- Default verification removes live permission and is network-free with respect to official sites.

## Evidence/data boundary

Git contains hashes, byte counts, public URLs, version bindings and deterministic expected outcomes,
not real response bodies. Controlled evidence totaled 1,487,105 bytes and was used locally for
replay. The Compose credentials are fixed test-only values bound to loopback ports in a disposable
isolated project.

No production credential, cookie, personal data, participant data or official-site access token was
found in the changed scope. Publication remains link-only; full-content redistribution, retention
policy, production robots refresh and counsel review remain Release Qualification work.
