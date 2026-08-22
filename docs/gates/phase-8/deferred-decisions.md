# Phase 8 Deferred Decisions

These items are deliberately outside the first Phase 8 engineering slice:

1. **Additional reminder variables.** New opportunity, deadline-near, cancellation, attachment
   replacement and other high-impact changes require separate necessity and one-variable designs.
2. **Real providers and channels.** Push, email, SMS, WeChat mini-program and provider credentials
   are absent; `TEST_INBOX` is the only implemented target.
3. **Frequency and orchestration.** The implemented cadence is fixed
   `AS_SOON_AS_GOVERNED`; digests, quiet hours, channel routing and multi-channel fallback are not
   approved. Users only have the independent deadline-change on/off control.
4. **Plans and calendar.** Calendar writes, material-plan scheduling, reminders near deadline and
   cross-device plan synchronization are not implemented.
5. **Operations console.** Bulk resend, campaign tooling, user lookup, provider dashboards and
   manual delivery mutation are absent.
6. **Production identity and privacy lifecycle.** Session lifecycle, rate limits, access/export,
   deletion, retention and provider-processing terms require separate design and validation.
7. **Human Release Qualification.** Real participants remain `0`; no open, complaint/close,
   comprehension, action, retention or payment evidence exists.
8. **Phase 6/7 qualification.** Their human tracks remain `NOT_STARTED` with
   `HOLD_MISSING_HUMAN_EVIDENCE`; Phase 8 engineering neither blocks nor qualifies them.
9. **Production operations and release.** Hosting, monitoring, backup/restore, incident response,
   deployment, public traffic and release remain unauthorized.
10. **Commercialization and Phase 9.** Pricing, institution workflows, paid placement, expansion
    and Phase 9 implementation have not begun.
11. **Contract stability.** v0.7 remains `IMPLEMENTED`; only a corresponding `QUALIFIED` Release
    Qualification could support a later `STABLE` decision.

These deferrals do not weaken exact evidence/version binding, user control, Outbox idempotency or
audit history. They prevent claims beyond the bounded synthetic engineering result.
