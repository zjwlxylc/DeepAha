# A6 S02 Real Acceptance v2

Evidence date: 2026-08-24 (Asia/Shanghai).

Result: `PASS_WITH_EXPLICIT_LIFECYCLE_GAPS`

## Selected evidence chain

The approved S02 route is the title-filtered MOHRSS public search endpoint through the generic
`OfficialAlternativeFetcher`. The bounded sample produced:

- RawArtifact `01a02f8c-02e1-73de-ba38-77a5e01aaf96`;
- SHA-256 `1b12bb32943fff5869d411ef74ca205d60a118cb66f0925017a1c9f3c3659641`;
- byte size `6,042` and a controlled object key derived from the hash;
- `VALID` AcquisitionEvaluation;
- Document `01a02f8c-034f-76d8-8b81-b6e1537707d0` with 10 replayed evidence locators;
- EvidenceRef `01a02f8c-0353-747a-8473-4e5561c38567`;
- stable Opportunity public ID `opp_2a13fa0b74328df54066f2104f712c55`, version `1`.

The chosen current result was “国家广播电视总局直属事业单位2026年度公开招聘公告（第二批）”.
Its deadline was not available in the validated search evidence, so status remains `UNKNOWN`; the
replay does not infer or fabricate a deadline.

## Replay and fail-closed proof

The controlled replay verifies source/endpoint/artifact binding, Recipe and endpoint-policy
versions, Fetcher/validator/parser versions, byte size, object SHA-256, validation status,
discovery result, normalized text hash, locator count and Opportunity identity with network
disabled. Repeating the resolution produces the same public ID and version rather than a duplicate.

Three current direct MOHRSS routes returned a JavaScript Cookie challenge. Their bytes and hashes
are preserved where policy permits, but common validation returns `CONTENT_CHALLENGE`; parsing is
`NOT_ATTEMPTED`, locator count is `0`, and no Document or Opportunity can be created from them.

## Explicit lifecycle gaps

The five bounded S02 samples cover direct root/list/detail challenge behavior and two valid official
search views. No current correction, cancellation or attachment-replacement variant was available
within the authorized sample. Those variants are `NOT_OBSERVED`, not synthetic evidence and not a
reason to loosen the validator. Production lifecycle coverage remains a future qualification item.
