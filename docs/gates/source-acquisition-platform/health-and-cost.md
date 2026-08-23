# Acquisition Health and Integration Cost

Status: `IMPLEMENTED`; first-five convergence result: `PASS` at A7.

## Semantic health

Health is derived at an explicit `as_of` time from immutable acquisition runs. A transport-level
HTTP success cannot by itself produce a healthy source result.

| Dimension | Derived meaning |
| --- | --- |
| Accessibility | Latest run reached approved semantically valid content, degraded, or stopped on an explicit challenge/access boundary |
| Discovery | Latest run discovered content, reported governed zero-discovery suspicion, or lacks enough evidence |
| Fetch integrity | Attempts reached persisted content validation rather than ending as transport failures |
| Parseability | VALID artifacts entered Document without counting invalid artifacts as parse candidates |
| Evidenceability | Parsed content produced replayable EvidenceRef locators |
| Drift | Persisted zero-discovery and selector-drift facts exceed the Recipe grace thresholds |

The summary also reports last semantically valid success, consecutive semantic failures, fixed
run counts, zero-discovery/selector-drift counts and browser/manual attempt ratios. Future-dated
runs relative to `as_of` fail closed.

## Integration-cost evidence

Each source records Recipe lines, source-specific production LOC, generic capability changes, core
schema changes, onboarding minutes, request/browser/manual/failure counts, maintenance minutes and
whether it reused an existing Fetcher. Evidence is immutable and idempotent for the exact
Source/Endpoint/Recipe version.

The first-five Gate refuses to calculate PASS with fewer than five distinct persisted sources. It
requires all of the following:

- at least 3/5 reuse an existing generic Fetcher;
- at least 3/5 use Recipe-only or Recipe plus a thin plugin;
- none changes the core product schema.

The versioned A7 manifest records five distinct sources:

- `4/5` (80%) reuse an existing generic Fetcher;
- `3/5` (60%) are Recipe-only;
- source-specific production LOC: `0`;
- core product schema changes: `0`;
- measured onboarding time: `185` minutes;
- bounded qualification requests: `13`, including `6` explicit failed attempts;
- persisted-evidence browser/manual requests: `0/0`.

These figures prove only early architectural convergence. They do not satisfy the separate
100-source/14-day maintenance target.
