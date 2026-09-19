# SG6 Final Verification

Candidate: `DeepAha 3.6.0-rc1 / SG6`.

## Product regression

After the final production-code change, all 18 `backend/tests/product/test_*.py` files were executed in isolated pytest processes with `-o addopts=`. Result: **176 passed / 0 failed**. The per-file evidence is `product_tests_by_file.txt`.

SG6-specific coverage includes:

- durable action timeline and remove-history export;
- outcome feedback → personal action-state transition without Eligibility mutation;
- deadline/change/weekly notification preferences;
- corrected deadline cancellation and rescheduling;
- weekly digest idempotency and scheduler behavior;
- personal erase semantics;
- API/profile/action-loop contract;
- backup-first SG6 additive upgrade and idempotency;
- front-end action/weekly/feedback-management contract.

## Static verification

- all `web/public/product/*.js` pass `node --check`;
- `check-product.mjs` PASS;
- `check-sg5.mjs` PASS;
- `check-sg5-1.mjs` PASS;
- `check-sg6.mjs` PASS;
- `python -m compileall -q backend/src/deepaha/product` PASS.

## Real multi-WMA data replay

Source: a fresh copy of the user-supplied multi-WMA data directory. The uploaded source bytes were never modified. Evidence: `REAL_WMA_SG6_ACCEPTANCE.json`.

Observed on the copied store:

- current actionable targets: **328**;
- SG5.1 first refresh: backup verified, 328 targets refreshed;
- SG6 first upgrade: backup verified, additive schema created;
- SG6 second upgrade: `already_current=true`, `data_modified=false`;
- pre-existing Opportunity/Unit/Decision/Publication/Revision/Snapshot/Task/Catalog/Account/Profile table digests and object-store digest were unchanged by SG6 schema upgrade;
- selected real target safe deadline: `2026-10-31`;
- saving that target created **3** automatic safe deadline schedules (30/7/1 days);
- action history recorded `SAVED → PREPARING → WAITING` (WAITING came from `INTERVIEW` outcome);
- entering WAITING cancelled the still-active application-deadline reminders;
- Eligibility before/after feedback remained the same (`UNCERTAIN` in this real example);
- feedback became a de-identified `CANDIDATE`; username and free-text content are not exposed in management output;
- weekly digest reflected the ongoing action and returned 3 new opportunities;
- weekly scheduled notice was created once and deduplicated on the second run;
- approved-source scheduling produced a queued `RECHECK` task for “宁波求职补贴” without executing WMA;
- WMA calls during this SG6 acceptance replay: **0**.

## UI / interaction proof

Native Chromium navigation to loopback remains blocked by administrator policy. SG6 therefore uses the same explicit HTTP TestClient bridge used by earlier accepted stages; the real product JS/CSS is rendered in Chromium and business requests are forwarded to real FastAPI + the copied SQLite database. This does not certify native cookie/CSP/network behavior.

Passed checks (`browser_acceptance.json`):

1. mobile Actions page + weekly digest;
2. action timeline modal;
3. independent deadline/change/weekly notification controls;
4. notifications + weekly summary;
5. operator de-identified feedback-candidate page;
6. 390px mobile no horizontal overflow;
7. page errors: **0**.

Screenshots: `screenshots/01_actions_mobile.png`, `02_action_timeline.png`, `03_notification_preferences.png`, `04_feedback_candidates_desktop.png`.

## Boundary

SG6 is an in-app action/notification/feedback loop. It does **not** claim WeChat/SMS/email delivery, does not directly modify rules from user feedback, does not train a model, and does not implement SG7 Gold/digital-twin/founding-user experiments. Windows native browser behavior remains pending user acceptance.
