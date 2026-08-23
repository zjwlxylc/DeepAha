# A7 Multi-source Reuse Evidence

Evidence date: 2026-08-24 (Asia/Shanghai).

Result: `PASS` for the bounded five-source Engineering Gate proof.

## Heterogeneous real-source evidence

| Source / role | Strategy | Current replay evidence | Integration mode | Source-specific production LOC |
| --- | --- | --- | --- | ---: |
| S02 MOHRSS recruitment | `OFFICIAL_ALTERNATIVE` | VALID HTML, 10 locators, complete Opportunity path | generic capability | 0 |
| S03 Zhejiang public recruitment | `STATIC_HTTP` | VALID detail HTML, 3 attachment links, 94 locators | generic capability | 0 |
| CRRC recruitment | `STATIC_HTTP` | VALID corporate HTML, official ATS discovery, 225 locators | Recipe-only | 0 |
| GQT notice/PDF substitute for inaccessible S04 route | `STATIC_HTTP` | root discovers 2 PDFs; PDF VALID with 22 locators | Recipe-only | 0 |
| MOE public disclosure substitute for unavailable S07/S05 route | `STATIC_HTTP` | VALID HTML, 351 locators | Recipe-only | 0 |

The Zhejiang attachment route exercised bounded attachment discovery. Its subsequent cross-host
redirect was outside the approved host set and failed safely; no host was silently expanded. The
CRRC ATS shell was retained as a valid transport result but produced the explicit
`HTML_TEXT_EMPTY` parse failure rather than being counted as a Document success.

S04 SASAC desktop/mobile routes returned challenge/network failure and have no active Recipe. The
approved design permits the nearest heterogeneous official substitute when a named route is
currently unavailable; GQT PDF evidence supplies the attachment/PDF shape without disguising the
S04 failure. China Mobile was inspected only for A5 feasibility: its public browser shell relied on
signed APIs, so no signature reconstruction, BrowserFetcher or persisted acquisition route was
implemented.

## Replay corpus

The manifest contains 16 real entries from 7 source groups, totaling 1,487,105 controlled bytes:

- validation: 9 `VALID`, 5 `CONTENT_CHALLENGE`, 2 `ZERO_DISCOVERY_SUSPECT`;
- parse: 8 `SUCCEEDED`, 1 explicit `FAILED`, 7 `NOT_ATTEMPTED`;
- all 16 object sizes/hashes and deterministic results replayed successfully with network disabled.

Actual response bodies remain outside Git in controlled local storage. The repository contains
only provenance, hashes, expected deterministic outcomes and version bindings.

## Convergence result

The persisted first-five integration evidence proves `4/5` existing-Fetcher reuse and `3/5`
Recipe-only onboarding. All five record zero source-specific production LOC and zero core schema
changes. This is early reuse evidence, not the 100-source/14-day Release Qualification.
