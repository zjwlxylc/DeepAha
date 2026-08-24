# P9-A Source Acquisition Platform Acceptance Results

Evidence date: 2026-08-24.

Final independent revalidation: `PASS` (`P0=0 / P1=0 / P2=0`)

Audit base: `cedce6f229dc341bf20107200b61e1f197b0d3d7`

Candidate: `94741c19a3a8471866930a46f7e70d85b7e79a68`

Audit range: `cedce6f229dc341bf20107200b61e1f197b0d3d7..94741c19a3a8471866930a46f7e70d85b7e79a68`

| Gate 0 criterion | Result | Reproducible evidence |
| --- | --- | --- |
| S02 complete approved path | PASS | one test consumes the exact corpus entry with socket/DNS disabled, then persists RawArtifact -> VALID evaluation -> production Document/10 locators -> persisted EvidenceRef -> stable Opportunity v1 |
| Invalid/challenge cannot enter Document | PASS | production DocumentService now rejects every evaluated Artifact unless all persisted evaluations are VALID; direct-service bypass regression and challenge tests pass |
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
- repair P9-A verifier: exit `0`, including root, Phase 2, Phase 8, migrations and replay;
- final independent read-only revalidation: `PASS`, with `P0=0 / P1=0 / P2=0`;
- implementation `IMPLEMENTED`; Engineering Gate `CLOSED`;
- Release Qualification `NOT_STARTED`; 100-source/14-day target `NOT_RUN`;
- contract maturity `IMPLEMENTED`, not `STABLE`.
