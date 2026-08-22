# Phase 5 Browser Verification

Date: 2026-08-22 (Asia/Shanghai)

Evidence class: local synthetic engineering evidence only. This document is not real Gold
qualification, production-readiness evidence, or Release Qualification evidence.

## Isolated runtime

- Compose projects used: `deepaha-phase5-browser-b3fb` and the final replay
  `deepaha-phase5-browser-final-b3fb`.
- PostgreSQL: `127.0.0.1:55435`; Moto: `127.0.0.1:55003`.
- API/Web application ports: `127.0.0.1:58005` and `127.0.0.1:58006`.
- Seed output: `SYNTHETIC_FIXTURE_ONLY inserted=3` with three deterministic public IDs.
- Final fixture SHA-256:
  `0dc0f1899338b8ec6e8935441f5b913fce70bca2096976cfa7845e626d861b89`.
- No Phase 2, Phase 3, or Phase 4 service, port, database, object store, or worktree was
  invoked, stopped, rebuilt, or occupied. Passive `docker compose ls` inspection continued
  to show the pre-existing `deepaha-phase2-live-gate` as running.

## Playwright rendered checks

The bundled Playwright CLI was used with named sessions. Two passes were performed: the first
covered navigation, finite filtering, loading/empty/error/recovery behavior and keyboard flow;
the second replayed the final fixture bytes after removing a percentage-like synthetic title.

| Check | Observed result |
| --- | --- |
| Desktop viewport | `1440x900`; list and detail had `scrollWidth - clientWidth = 0` |
| Mobile viewport | `375x812`; three cards, fixture boundary visible, no horizontal overflow |
| Mobile typography and targets | body `16px`; business controls measured `44` to `51px` high |
| Keyboard entry | first Tab focused `跳到主要内容`; computed outline was `solid`; Enter moved URL to `#main-content` |
| Populated list | three governed `LICENSE_SAFE_FIXTURE` cards with stable IDs, status, dates and verification time |
| Search | literal `%` query selected one fixture; nonexistent text reached the explicit empty state |
| Finite filters | type `SCHOLARSHIP`, status `OPEN`, and region `合成宁波市` each produced one deterministic result |
| Sort and pagination | `DEADLINE_ASC` first date was `2026-08-31`; `limit=1` exposed a cursor-bound next link |
| Loading and empty | streamed loading state was visible before `没有找到符合条件的公开机会` |
| Detail | official entry plus attachment used `_blank`/`noreferrer`; 10 EvidenceRef cards and ordered history rendered |
| Phase 6 boundary | `个人判断尚未开放`; zero inputs, textareas or selects; no profile was collected |
| Negative claims | no eligibility state, match percentage, model confidence or `92%` claim; final titles contained no numeric percentage |
| Final console | home -> list -> detail -> fit-check replay completed with `0` errors and `0` warnings |

## Controlled failure and recovery

Only the Phase 5 browser project's PostgreSQL container was stopped. The public page rendered
`暂时无法加载公开机会`, did not substitute an empty result, showed `重新加载`, and exposed no
SQLAlchemy, psycopg, traceback, password, or connection detail.

The compose file intentionally uses `tmpfs`, so restarting PostgreSQL recreated the disposable
database. Migrations and the same three synthetic rows were replayed. A RED/GREEN client test
then established `cache: no-store`; after that change, the rendered retry recovered immediately
to the expected empty search result instead of reusing a cached 503 response.

## Visual inspection and artifact boundary

- Final screenshots were captured outside the repository at
  `%TEMP%/deepaha-phase5-browser-b3fb/final-mobile-list.png` and
  `%TEMP%/deepaha-phase5-browser-b3fb/final-desktop-detail.png` and visually inspected.
- The mobile composition kept the fixture warning before filters and results, stacked controls
  without clipping, and separated public facts from the Phase 6 entry.
- The desktop detail kept current facts, official actions, EvidenceRef cards, history, and the
  Phase 6 boundary visually distinct.
- The visible black `N` in development screenshots is the Next.js development overlay, not a
  production asset or committed UI.
- No screenshot, Playwright state, trace, cookie, generated agent file, or console log is tracked.
- `/favicon.ico` returns `204` with `X-DeepAha-Brand-Asset:
  pending-clean-approved-icon`; the watermarked source raster and an invented replacement are
  both excluded until a clean approved icon exists.

## Remaining qualification boundary

This evidence used exactly three license-safe synthetic records. It does not establish the
required 200 real, permission-clear, verified Gold opportunities, 100% public trustworthy-field
completeness, reproducible official-link coverage, or real-candidate freshness. Release
Qualification therefore remains `NOT_STARTED`. The completed browser evidence, the rest of the
Gate package and all six successful jobs for exact candidate SHA
`492c8b34562dca59c2a66d6e4d3ea769345803ca` in run `32549701629` support Engineering Gate
`CLOSED`; they do not support release or production qualification.
