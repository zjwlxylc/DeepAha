# Phase 5 Code Review

Review scope: `8840fe33bd3946a10a5b4448a59f2bf4d7622c3d..cc5e240`.

Because this task explicitly prohibited sub-agents, the required review was performed in the
primary session against the full diff, plan, Blueprint boundary and executable tests. No Critical
or Important finding remains open.

## Findings resolved

1. **Important — inferential evidence could enter the public projection.** The first implementation
   required an official EvidenceRef but did not reject precedence 100 semantic inference. A RED
   PostgreSQL case reproduced publication; commit `cc5e240` now excludes all candidates containing
   field evidence below official FAQ/guidance level (`precedence < 300`). The focused integration
   file passes 16 cases after the fix.
2. **Important — retry reused a failed response.** Browser failure/recovery showed that
   `revalidate: 60` could retain a 503 across explicit retry. A RED client test led to
   `cache: no-store`; rendered retry now recovers immediately.
3. **Important — percentage-like synthetic title.** Visual review found `100%` in a synthetic
   fixture title. A RED fixture-policy test led to a percentage-free title while retaining literal
   `%/_` search coverage and an updated manifest hash.
4. **Minor — favicon and route-transition console noise.** The watermarked raster remained
   excluded; a tested 204 asset-boundary route and explicit smooth-scroll declaration reduced the
   final browser console to 0 errors / 0 warnings.

## Scope and architecture review

- Every changed production path maps to public catalog governance, projection, GET API or Web/PWA.
- The service reads existing Opportunity/Version/Event/Evidence/Source records; no v0.5 domain
  contract or schema family was introduced.
- Search is literal and in-memory over the finite governed set; no personalized or semantic ranker
  exists.
- Stable sort keys and cursor binding prevent duplicate/skip behavior on an unchanged catalog.
- Public DTOs omit storage URIs, reviewer identity, profiles, rules, eligibility and model values.
- The Phase 6 route is an honest static boundary with no form or write behavior.
- No unrelated refactor, upstream workspace mutation, merge or release is included.

## Current decision

Implementation is `IMPLEMENTED`. With exact candidate SHA
`492c8b34562dca59c2a66d6e4d3ea769345803ca` passing all six jobs in GitHub Actions run
`32549701629`, the Engineering Gate is `CLOSED`. Phase 5 Public API Contract Maturity remains
`IMPLEMENTED`, not `STABLE`, and Release Qualification remains `NOT_STARTED`.
