# P9-B Gateway Replacement Implementation Boundary

Decision date: 2026-08-25 (Asia/Shanghai)

Decision status: `APPROVED / REPLACEMENT IMPLEMENTATION AUTHORIZED`

This file records the implementation boundary fixed by the approved P9-B Gateway unified
architecture review. It does not add conditions from any other review, report or proposal.

## 1. Fixed Git and status boundaries

- Replacement branch point: `961891125237cfdd00068bcbee6893e45c96fcdc`.
- Complete candidate review range remains
  `94741c19a3a8471866930a46f7e70d85b7e79a68..replacement-head`.
- The previous Gateway candidate and its Gateway migrations are not an implementation base.
- P9-B Engineering Gate remains `OPEN`.
- P9-B Release Qualification remains `NOT_STARTED`.
- P9-B Contract maturity remains `IMPLEMENTED`, not `STABLE`.
- This implementation does not authorize merge, push, deployment, live Provider access or
  Release Qualification.
- Internal verification is not independent acceptance. Independent acceptance must use a new
  task and a fresh clean worktree after implementation stops.

## 2. Fixed persistence architecture

The replacement Gateway owns three relational write models and one read-only projection:

1. `p9b_model_calls` stores the immutable call intent. The upstream `model_call_id` is stable and
   idempotent only when the canonical request hash is identical; reusing the identifier with a
   different hash is a conflict.
2. `p9b_model_call_attempts` stores one row per `(model_call_id, attempt_number)`. It records the
   database authorization decision and `clock_timestamp()` at attempt start, then accepts exactly
   one terminal result transition after dispatch.
3. `p9b_model_call_finalizations` stores exactly one database-derived finalization per call.
   Application callers cannot freely declare `SUCCEEDED` or `TERMINAL_FAILED`.
4. `p9b_model_call_ledger_view` derives status, counts, ordered attempts, response metadata,
   token use, cost and latency. Callers do not persist duplicated status/count/attempt JSON.

Authorization columns are immutable. Attempt result columns transition only from `NULL` to one
terminal outcome. Direct SQL must not be able to forge an authorized dispatch or successful
finalization without the required revision, Egress and attempt facts.

## 3. Fixed transaction and concurrency flow

The only Provider path is:

```text
register_model_call()
  -> begin_attempt() short transaction
  -> adapter.invoke() outside the database transaction
  -> finish_attempt() short transaction
  -> finalize_model_call() short transaction
```

`begin_attempt()` locks the SourceBundle Revision, reads attempt time with PostgreSQL
`clock_timestamp()`, validates the complete Egress authority and commits either `AUTHORIZED` or
`AUTHORITY_REJECTED` before any Provider invocation. An authorization rejection never invokes a
Provider.

`finish_attempt()` records the observed Provider outcome once and does not require current
authorization, so an outcome cannot disappear when authority expires or a Revision is invalidated
after dispatch.

`finalize_model_call()` uses the same Revision lock order as begin-attempt and invalidation. A
valid result may finalize as `SUCCEEDED` only while the Revision remains valid. An invalidated
Revision finalizes as `TERMINAL_FAILED / REVISION_INVALIDATED_AFTER_DISPATCH` while retaining the
attempt audit. Provider duration never holds the Revision lock or a database transaction open.

## 4. Fixed retry, idempotency and unknown-outcome rules

- Every call has a stable local `model_call_id`; every attempt has a unique monotonic number and a
  stable attempt identifier.
- An adapter that explicitly supports Provider idempotency receives the stable attempt identifier
  as its idempotency key.
- Explicit retryable Provider responses such as governed `429` and `5xx` results may be retried.
- Without explicit Provider idempotency capability, an ambiguous transport failure becomes
  `PROVIDER_OUTCOME_UNKNOWN` and is not retried.
- An authorized attempt that remains unfinished beyond its dispatch deadline is reconciled to
  `PROVIDER_OUTCOME_UNKNOWN`. Reconciliation is bounded and may run at Gateway startup, before a
  later call or through an explicit operations command; no new daemon is introduced.

## 5. Fixed value-level contract

- `retention_class` is an enum consistent with the persisted policy snapshot.
- `raw_response_reference` is a structured internal object reference or a bounded Provider
  response identifier, never an arbitrary URL.
- `provider_response_id` is bounded, control-character-free and credential-token guarded.
- Provider/model/adapter/prompt/parser/schema/contract values use bounded safe identifiers.
- Generation parameters are limited to governed numeric `temperature`, `top_p` and `seed` fields.
- Attempt history is relational; arbitrary nested caller JSON is not persisted.
- Every remaining free string is checked by the defense-in-depth credential scanner.
- Pydantic validation, database functions and migration history preflight share the same positive
  and negative corpus and must not drift.
- No Provider runtime registry, database role redesign or `SECURITY DEFINER` privilege model is
  added.

## 6. Migration replacement boundary

- Migrations `20260824_0011` through `20260824_0014` remain exact historical ancestors.
- Effective non-Gateway corrections may be ported selectively from later commits.
- Old Gateway migrations `20260824_0015`, `20260825_0018`, `20260825_0020` and
  `20260825_0022` are discarded rather than edited or retained wholesale.
- Replacement Gateway migrations use new unique revision identifiers and must prove fresh upgrade,
  downgrade/re-upgrade, compliant and non-compliant history preflight, old-structure restoration
  where applicable, and zero Alembic schema drift.

## 7. Ordered implementation rounds and exit conditions

1. **Replacement cut and non-Gateway closure.** Port only approved non-Gateway fixes; all legacy
   P9-B boundaries pass and no Gateway table exists.
2. **Call/attempt/finalization state.** PostgreSQL constraints and tests prove that direct SQL
   cannot forge authority or success, and invalid metadata still produces an auditable terminal
   record.
3. **Authorization and Revision concurrency.** Tests prove expired-before-first means zero Provider
   calls plus rejection audit; expiry during retry retains the first outcome; valid retry succeeds;
   lock order has no regression; invalidation retains audit and cannot finalize success.
4. **Idempotency and unknown outcome.** Tests prove stable identifiers, hash-conflict rejection,
   governed `429`/`5xx` retry, ambiguous no-retry and stale-attempt reconciliation.
5. **Ledger contract and migrations.** The complete string inventory and shared corpus have
   application/database/preflight parity; fresh upgrade, round trip, history preflight and schema
   drift checks pass.
6. **Verifier and internal full verification.** Verifiers use task-owned dynamic resources, remain
   compatible with detached HEAD, tolerate previously occupied legacy ports, run concurrent
   isolated Compose smoke checks and clean only their own resources. The full P9-B verifier passes.

Every round ends in one local commit only after its exit condition passes. If an exit condition
fails, implementation stops; the architecture is not changed to bypass it.
