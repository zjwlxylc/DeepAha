# Phase 8 Real-Browser Engineering Verification

## Evidence boundary

- Candidate: `6586f4b784afb05b0a5070d07a379dc663372e92`.
- Browser: real Playwright-managed Chromium against production-built Next.js and a real local
  FastAPI/PostgreSQL stack.
- Data and identity: fixed synthetic fixture and fixture-only owner session; no real participant.
- Delivery: local PostgreSQL `TEST_INBOX`, not a push/email/mini-program/provider delivery.

## Automated journey

1. Seed exactly one governed deadline-extension reminder from OpportunityVersion 6 to 7.
2. At `1280x900`, open `/me/reminders` as the fixed owner and observe one immutable inbox record.
3. Verify old/new dates `2026-09-20` and `2026-09-30`, direction `EXTENDED`, version `6 → 7`, both
   official evidence links and the stable personal-action link.
4. Use only keyboard navigation to disable and save the reminder preference. Confirm the control
   reads disabled while the historical inbox record remains.
5. Use only keyboard navigation to re-enable and save, then reload at `390x844`.
6. Confirm the record remains owner-visible, the mobile document has no horizontal overflow and
   the page emitted no browser console error/warning or page error.

The test starts and stops API/Web processes itself; `8008` and `3088` are checked before use and
released afterward. Playwright traces, screenshots, video and reports are not committed.

## Not measured

The successful browser journey proves rendering, keyboard control, exact fact projection and local
API behavior. It does not measure a human open, complaint, close, comprehension, action, retention
or willingness-to-pay rate. It does not validate a real notification provider, production identity,
mini-program, calendar or public release.
