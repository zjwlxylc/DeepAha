#!/usr/local/bin/python3.13 -I
"""Operator-only authorization via an authenticated root terminal, never sudo-delegated.

The Gateway cannot invoke this program or write the approval directory. No approval
is created by deployment/setup. A human independently reviews the exact binding.
"""

import json
import os
from pathlib import Path
import re
import sys
import time
import uuid


def main():
    if os.geteuid() != 0 or not sys.stdin.isatty():
        raise SystemExit("Authenticated root terminal required")
    if len(sys.argv) != 4:
        raise SystemExit("Usage: authorize ACTION EXPECTED_CURRENT TARGET")
    action, expected, target = sys.argv[1:]
    if action not in ("deploy", "rollback", "backup", "restart") or not re.fullmatch(
        "[0-9a-f]{40}", expected
    ):
        raise SystemExit("Invalid binding")
    if action in ("deploy", "rollback") and not re.fullmatch("[0-9a-f]{40}", target):
        raise SystemExit("Invalid target")
    if action == "restart" and target not in ("api", "worker", "all"):
        raise SystemExit("Invalid target")
    if action == "backup" and target != "-":
        raise SystemExit("Invalid target")
    binding = {
        "action": action,
        "environment": "production",
        "expected_current": expected,
        "target": target,
    }
    print(json.dumps(binding, indent=2))
    challenge = uuid.uuid4().hex[:12]
    print(
        "Review production impact independently. To authorize once for 5 minutes, type: "
        + challenge
    )
    if input("Approval: ") != challenge:
        raise SystemExit("Not authorized")
    identifier = uuid.uuid4().hex
    directory = Path("/var/lib/deepaha-ops-trust/approvals")
    os.umask(0o077)
    with (directory / (identifier + ".json")).open("x") as f:
        json.dump(
            {
                "binding": binding,
                "expires_at": time.time() + 300,
                "authority": "authenticated-root-operator",
            },
            f,
        )
        f.flush()
        os.fsync(f.fileno())
    print("approval_id=" + identifier)


if __name__ == "__main__":
    main()
