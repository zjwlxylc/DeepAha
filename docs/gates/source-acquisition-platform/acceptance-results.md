# P9-A Source Acquisition Platform Acceptance Results

Evidence date: 2026-08-24.

| Gate 0 criterion | Result | Reproducible evidence |
| --- | --- | --- |
| S02 complete approved path | PASS | official-alternative RawArtifact -> VALID evaluation -> Document/10 locators -> EvidenceRef -> stable Opportunity v1 |
| Invalid/challenge cannot enter Document | PASS | five real challenge samples plus synthetic CAPTCHA/login/access-denied tests; parse not attempted |
| Offline replay and binding | PASS | 16 real objects verify size/hash/version/binding/result with network disabled |
| Materially different official sources | PASS | HTML list/detail, corporate ATS discovery, PDF attachment and public disclosure use one control plane |
| Existing generic Fetcher reuse | PASS | `4/5` (80%), threshold `>=3/5` |
| Recipe/thin-logic convergence | PASS | `3/5` (60%) Recipe-only; no thin plugin required |
| No source-specific platform duplication | PASS | source-specific production LOC `0`; production-domain scan empty |
| Visible semantic failure modes | PASS | real challenge/zero-discovery/parse failure; deterministic selector-drift/unexpected-content tests |
| Safe CAPTCHA/login/access degradation | PASS | explicit terminal statuses, retained evidence where permitted, zero Document advancement |
| Measured onboarding/cost convergence | PASS | 185 minutes, 13 requests, 6 explicit failures, browser/manual `0/0`, core schema changes `0` |

Additional acceptance facts:

- controlled corpus: 16 entries, 7 source groups, 1,487,105 bytes;
- validation: 9 VALID, 5 CONTENT_CHALLENGE, 2 ZERO_DISCOVERY_SUSPECT;
- complete P9-A verifier: exit `0`, including root, Phase 2, Phase 8, migrations and replay;
- implementation `IMPLEMENTED`; Engineering Gate `CLOSED`;
- Release Qualification `NOT_STARTED`; 100-source/14-day target `NOT_RUN`;
- contract maturity `IMPLEMENTED`, not `STABLE`.
