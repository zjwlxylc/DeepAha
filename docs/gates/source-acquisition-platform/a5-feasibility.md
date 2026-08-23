# A5 Real Strategy Feasibility

Evidence date: 2026-08-24 (Asia/Shanghai).

Status: `COMPLETED`

This record is populated only from bounded, explicitly authorized checks against public official
endpoints. It must not contain response bodies, cookies, credentials, unredacted headers or claims
that a transport-level success is valid source content.

## Qualification command boundary

- Live execution requires both the `-Live` wrapper switch and the process-local
  `DEEPAHA_ALLOW_LIVE_SOURCE_CHECK=true` permission set by that wrapper.
- Each run declares the exact Recipe and endpoint IDs, a total request cap of at most 25 and a
  positive minimum interval.
- Output is an allowlisted JSON summary. Any challenge, policy, unavailable strategy or exhausted
  budget produces a nonzero exit.

## S02 current evidence

Five bounded current samples were retained in controlled object storage and committed only as
metadata in `config/acquisition/real-source-corpus.v1.json`:

| Route | Result | Bytes | SHA-256 prefix | Consequence |
| --- | --- | ---: | --- | --- |
| MOHRSS recruitment root | `CONTENT_CHALLENGE` | 984 | `a36c4d24c412` | retained RawArtifact; no Document |
| MOHRSS recruitment page 2 | `CONTENT_CHALLENGE` | 984 | `e71d2292099d` | retained RawArtifact; no Document |
| MOHRSS unfiltered official search | `VALID` | 5,927 | `b9ce5569a90a` | Document; 10 locators |
| MOHRSS current detail | `CONTENT_CHALLENGE` | 985 | `d58273555574` | retained RawArtifact; no Document |
| MOHRSS title-filtered official search | `VALID` | 6,042 | `1b12bb32943f` | Document; 10 locators; selected path |

The endpoint policy records the checked robots/use boundary, a six-hour minimum interval,
approved hosts and link-only publication. The checks did not execute challenge code, retain
cookies, reconstruct signed requests or bypass access controls.

## Strategy decision

Selected: `L3_OFFICIAL_ALTERNATIVE` using the title-filtered public MOHRSS search endpoint and the
generic `OfficialAlternativeFetcher`.

- L0 structured feed: no approved current structured endpoint was found.
- L1 direct static page: the root, list page and current detail returned a JavaScript Cookie
  challenge and therefore fail closed.
- L2 standard Browser: not selected. A browser implementation was neither required nor justified
  after L3 produced semantically valid public official content; no BrowserFetcher was added.
- L4 governed manual: unnecessary for the selected S02 proof and not implemented.

The selected path preserves the same host, redirect, MIME, size, retry, RawArtifact, validation,
Document and replay controls as the generic static Fetcher. It is an approved official discovery
alternative, not a challenge bypass.
