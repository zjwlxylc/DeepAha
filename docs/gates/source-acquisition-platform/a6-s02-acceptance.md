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
- a Document created by the production `DocumentService`, with 10 replayed evidence locators;
- an EvidenceRef selected from those persisted locators by its retained quote hash;
- stable Opportunity public ID `opp_2a13fa0b74328df54066f2104f712c55`, version `1`.

The chosen current result was “国家广播电视总局直属事业单位2026年度公开招聘公告（第二批）”.
Its deadline was not available in the validated search evidence, so status remains `UNKNOWN`; the
replay does not infer or fabricate a deadline.

## Replay and fail-closed proof

The S02 Opportunity acceptance consumes `source_acquisition_entry_id` to select the exact entry in
the 16-object corpus. With socket creation, connection and DNS resolution disabled, it runs the
common replay validator/parser, persists the bound RawArtifact and CaptureObservation, records the
resulting `VALID` AcquisitionEvaluation, invokes the production Document admission and parser,
selects a real persisted EvidenceRef, and only then calls the existing Opportunity resolution
service. It verifies source/endpoint/artifact and component-version binding, byte size, object
SHA-256, normalized text hash, locator count, Document idempotency and Opportunity identity.
Repeating both transitions produces neither a duplicate Document nor a duplicate Opportunity.

Three current direct MOHRSS routes returned a JavaScript Cookie challenge. Their bytes and hashes
are preserved where policy permits, but common validation returns `CONTENT_CHALLENGE`; parsing is
`NOT_ATTEMPTED`, locator count is `0`, and no Document or Opportunity can be created from them.

## Explicit lifecycle gaps

The five bounded S02 samples cover direct root/list/detail challenge behavior and two valid official
search views. No current correction, cancellation or attachment-replacement variant was available
within the authorized sample. Those variants are `NOT_OBSERVED`, not synthetic evidence and not a
reason to loosen the validator. Production lifecycle coverage remains a future qualification item.
