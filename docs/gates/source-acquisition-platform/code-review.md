# P9-A Final Code Review

Evidence date: 2026-08-24. The original review is superseded by the first independent acceptance.

Result: `REPAIR_VERIFIED`; independent confirmation pending.

The first independent acceptance found two P1 issues: the S02 Opportunity test manually seeded
Document/Evidence instead of consuming replay output, and the VALID-only rule could be bypassed by
calling `DocumentService.parse` directly. The repair candidate removes both conditions and passes
the complete isolated verifier. A fresh independent read-only acceptance has been requested for
the exact repair candidate.

## Review scope and conclusions

- Reviewed every changed path from A0 ancestor `9d05104` through the code candidate.
- Production acquisition modules contain no named-source domains or source IDs; all current-site
  facts are confined to versioned endpoint/Recipe/evidence manifests.
- There is no source-specific implementation of transport, retry, persistence, content validation,
  replay, health, drift, evidence storage or Opportunity resolution.
- The only existing collector change adds policy-bounded dynamic URLs, request limits, redirect
  provenance and optional unexpected-content capture; it retains the existing public-host and SSRF
  checks.
- New migrations are additive companion tables. No Opportunity, Eligibility, RuleSet or user schema
  changed for acquisition.
- Orchestration is bounded by Recipe request/elapsed/discovery limits and does not recursively crawl
  detail pages; only permitted attachment discovery is queued from a detail.
- Replay verifies bytes, SHA-256, IDs and component versions before deterministic validation and
  parsing; missing controlled bytes report `BLOCKED`, never synthetic `PASS`.
- The isolated verifier invokes the root, Phase 2 and Phase 8 verifiers, excludes live official-site
  access and tears down only its exact Compose project.
- Secret/bypass/domain scans and `git diff --check` returned no finding.

The new independent review must still assess the complete base-to-candidate range. It does not
assess future scheduler, production deployment, legal approval or the 100-source/14-day Release
Qualification.
