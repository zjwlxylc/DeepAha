# Controlled operations contract

REST and MCP share GatewayCore. Business requests require an explicit environment;
scopes use `environment:action`. No model credential can create production approvals.
The global switch and staging switch default off. Beta user creation is disabled.

Mutations require a body `idempotency_key` and full `expected_current` SHA. Deploy
and rollback accept only full target SHAs. The host registry must independently bind
the private repository, artifact digest/file hashes, schema fingerprint, test evidence,
environment and compatible source SHAs. Unknown SHAs are never fetched or built by
the privileged adapter. Production candidates and staging probes are distinct.

The fixed adapter and binding are root-owned. All supported direct operator commands
invoke the same adapter and per-environment flock. Legacy package deployment scripts
are historical artifacts and must not be used as an alternative deployment path.
No sudo rule grants the Gateway access to the approval issuer or generic commands.

Production approval uses an independently authenticated operator terminal and the
root-only `authorize.py` helper, exact action/current/target binding, five-minute
expiry and atomic one-use consumption. Model-filled confirmation text is rejected.
The live production binding may remain disabled even when the gate is installed;
enabling it is a separate human-controlled configuration change. This installation
does not test production mutations or authorize any production version.

Backup pauses only the selected environment's API/Worker, captures PostgreSQL and
objects, verifies the dump and hashes, then restores previously active services.
Secrets are excluded and provisioned separately. Restore drills use a separate empty
database and object directory; no restore or SQL tool is exposed to MCP/REST.
Rollback changes application symlink only and must never be described as DB recovery.

Audit append/chain failure closes mutation admission. Queued/running work after a
Gateway restart becomes UNKNOWN; reconcile host state before another operation.
The bounded worker does not automatically replay unfinished work. Hash chains are
local tamper evidence, not protection against a privileged root attacker.

MCP uses the official SDK, Streamable HTTP at `/mcp`, and RFC 7662 introspection
against a separately configured OAuth provider. PKCE, login, consent, refresh and
revocation belong to that provider. Resource metadata advertises scopes; the verifier
requires a live token for the exact resource/issuer and core checks each tool scope.
No API-key bypass is provided for web MCP. REST API keys remain hashed at rest.

`openapi.yaml` is generated OpenAPI JSON (valid YAML), usable for optional private GPT
Actions. Its idempotency key is in the body; writes are consequential. A server smoke
receipt does not prove that a user's ChatGPT account has connected. Account-side
login/consent must be performed by that user, and actual request receipts are needed.

Deploy only committed, tested source and retain the previous Gateway package, unit,
environment, adapter and sudoers for recovery. Do not reinitialize audit/state files.
Runtime dependencies are locked in `requirements.lock`; install as an unprivileged
build identity, then seal source/runtime read-only before service startup.
