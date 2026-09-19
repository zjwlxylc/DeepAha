#!/usr/local/bin/python3.13 -I
"""Fixed host adapter. The deployment-specific binding is root-owned and private.

No caller selects a path, command, database, SQL statement, unit or repository.
Product code is never imported here. All source builds happen outside this adapter.
"""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import urllib.request
import uuid

CONFIG = Path("/etc/deepaha-ops/adapter.json")
REGISTRY = Path("/var/lib/deepaha-ops-trust")
SHA = re.compile(r"[0-9a-f]{40}\Z")
META = {
    "schema_version": "1",
    "actionable_schema_version": "2",
    "action_loop_schema_version": "1",
    "opportunity_lab_schema_version": "2",
}
SCHEMA_QUERY = """SELECT json_build_object('columns',(SELECT json_agg(t ORDER BY table_name,ordinal_position) FROM (SELECT table_name,column_name,ordinal_position,data_type,udt_name,is_nullable,column_default,character_maximum_length FROM information_schema.columns WHERE table_schema='public') t),'constraints',(SELECT json_agg(t ORDER BY tab,conname) FROM (SELECT c.relname AS tab,p.conname,pg_get_constraintdef(p.oid) AS definition FROM pg_constraint p JOIN pg_class c ON c.oid=p.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public') t),'indexes',(SELECT json_agg(t ORDER BY tablename,indexname) FROM (SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public') t));"""


def reject(code):
    raise RuntimeError(code)


def trusted(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        reject("UNTRUSTED_FILE")
    return path


def load(path):
    return json.loads(trusted(path).read_text())


def file_hash(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def host_event(event, details):
    """Fail closed for privileged CLI too; local chain does not defeat a root attacker."""
    with open("/run/lock/deepaha-ops-host-audit.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = REGISTRY / "host-audit.jsonl"
        previous = "0" * 64
        if path.exists():
            trusted(path)
            with path.open() as f:
                for line in f:
                    row = json.loads(line)
                    digest = row.pop("hash")
                    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"))
                    if (
                        row["previous"] != previous
                        or hashlib.sha256(canonical.encode()).hexdigest() != digest
                    ):
                        reject("HOST_AUDIT_CORRUPTED")
                    previous = digest
        row = {"previous": previous, "event": event, "time": time.time(), "details": details}
        digest = hashlib.sha256(
            json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with path.open("a") as f:
            f.write(json.dumps({**row, "hash": digest}) + "\n")
            f.flush()
            os.fsync(f.fileno())


def done(result):
    host_event("completed", result)
    return result


def run(args, timeout=40, output=None):
    # Output is either small fixed metadata or streamed directly to a private file.
    p = subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        stdout=output or subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
        timeout=timeout,
    )
    if p.returncode:
        reject("HOST_COMMAND_FAILED")
    return p.stdout.decode().strip() if output is None else None


def sql(binding, query):
    return run(
        [
            "/usr/sbin/runuser",
            "-u",
            "postgres",
            "--",
            "/usr/bin/psql",
            "-X",
            "-A",
            "-t",
            "-v",
            "ON_ERROR_STOP=1",
            "-d",
            binding["database"],
            "-c",
            query,
        ]
    )


def schema(binding):
    rows = json.loads(sql(binding, SCHEMA_QUERY))
    meta = json.loads(
        sql(
            binding,
            "SELECT json_object_agg(key,value) FROM product_meta WHERE key IN ('schema_version','actionable_schema_version','action_loop_schema_version','opportunity_lab_schema_version')",
        )
    )
    if meta != META:
        reject("DATABASE_GENERATION_MISMATCH")
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def current(binding):
    actual = Path(binding["current"]).resolve(strict=True)
    if binding.get("legacy_release") == str(actual):
        return binding["legacy_sha"]
    if actual.parent != Path(binding["releases"]) or not SHA.fullmatch(actual.name):
        reject("CURRENT_BINDING_MISMATCH")
    return actual.name


def service(binding, verb, target="all"):
    keys = ["api", "worker"] if target == "all" else [target]
    run(["/usr/bin/systemctl", verb, *[binding["units"][k] for k in keys]], timeout=75)


def healthy(binding):
    for _ in range(30):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{binding['port']}/health/ready", timeout=2
            ) as r:
                if r.status == 200:
                    run(["/usr/bin/systemctl", "is-active", *binding["units"].values()])
                    return
        except Exception:
            pass
        time.sleep(1)
    reject("HEALTH_FAILED")


def release(binding, sha, old, environment):
    path = REGISTRY / "releases" / f"{sha}.json"
    if not path.exists():
        reject("RELEASE_NOT_APPROVED")
    manifest = load(path)
    if (
        manifest["sha"] != sha
        or manifest["repository"] != binding["repository"]
        or environment not in manifest["environments"]
    ):
        reject("RELEASE_NOT_APPROVED")
    if (
        manifest["schema_policy"] != "NO_SCHEMA_CHANGE"
        or manifest["tests"] != "PASS"
        or old not in manifest["compatible_with"]
    ):
        reject("RELEASE_INCOMPATIBLE")
    if schema(binding) != manifest["schema_fingerprint"]:
        reject("SCHEMA_CHANGE_REQUIRES_SEPARATE_MIGRATION")
    directory = Path(binding["releases"]) / sha
    if directory.is_symlink() or directory.stat().st_uid != 0 or directory.stat().st_mode & 0o022:
        reject("UNTRUSTED_RELEASE_DIRECTORY")
    files = {}
    for p in directory.rglob("*"):
        rel = p.relative_to(directory).as_posix()
        if p.is_symlink():
            if rel != ".venv-product" or str(p.resolve()) != binding["runtime"]:
                reject("RELEASE_SYMLINK")
            continue
        if p.is_file():
            files[rel] = file_hash(trusted(p))
        elif p.stat().st_uid != 0 or p.stat().st_mode & 0o022:
            reject("UNTRUSTED_RELEASE_DIRECTORY")
    if files != manifest["files"]:
        reject("ARTIFACT_MISMATCH")
    artifact = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if artifact != manifest["artifact_sha256"]:
        reject("ARTIFACT_MISMATCH")
    return directory


def switch(binding, directory):
    link = Path(binding["current"])
    temporary = link.with_name(link.name + ".ops-next")
    if temporary.exists() or temporary.is_symlink():
        reject("PENDING_SWITCH_EXISTS")
    temporary.symlink_to(directory)
    os.replace(temporary, link)


def backup(binding, sha):
    backup_id = uuid.uuid4().hex
    directory = Path(binding["backups"]) / backup_id
    directory.mkdir(mode=0o700)
    active = {
        key: subprocess.run(["/usr/bin/systemctl", "is-active", "--quiet", unit]).returncode == 0
        for key, unit in binding["units"].items()
    }
    try:
        service(binding, "stop")
        with (directory / "database.dump").open("wb") as f:
            run(
                [
                    "/usr/sbin/runuser",
                    "-u",
                    "postgres",
                    "--",
                    "/usr/bin/pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--dbname",
                    binding["database"],
                ],
                timeout=180,
                output=f,
            )
        # Unprivileged tar cannot read any production objects, even via malicious links.
        with (directory / "objects.tar").open("wb") as f:
            run(
                [
                    "/usr/sbin/runuser",
                    "-u",
                    binding["user"],
                    "--",
                    "/usr/bin/tar",
                    "-C",
                    binding["objects"],
                    "-cf",
                    "-",
                    ".",
                ],
                timeout=90,
                output=f,
            )
        run(["/usr/bin/pg_restore", "--list", str(directory / "database.dump")])
        metadata = {
            "backup_id": backup_id,
            "sha": sha,
            "schema_fingerprint": schema(binding),
            "scope": ["database including accounts and sessions", "objects"],
            "secrets": "excluded; provision independently",
            "consistency": "API and Worker stopped during both captures",
            "database_locale": json.loads(
                sql(
                    binding,
                    "SELECT json_build_object('collate',datcollate,'ctype',datctype) FROM pg_database WHERE datname=current_database()",
                )
            ),
            "files": {p.name: file_hash(p) for p in directory.iterdir() if p.is_file()},
        }
        (directory / "manifest.json").write_text(json.dumps(metadata, sort_keys=True))
        return {"backup_id": backup_id, "integrity": "VERIFIED", "consistency": "QUIESCED"}
    finally:
        for key, was_active in active.items():
            if was_active:
                service(binding, "start", key)


def receipt(approval, action, environment, expected, target):
    if not re.fullmatch("[0-9a-f]{32}", approval):
        reject("HUMAN_AUTH_REQUIRED")
    path = REGISTRY / "approvals" / f"{approval}.json"
    ticket = load(path)
    if ticket.get("expires_at", 0) < time.time() or ticket.get("expires_at", 0) > time.time() + 900:
        reject("HUMAN_AUTH_EXPIRED")
    if ticket.get("binding") != {
        "action": action,
        "environment": environment,
        "expected_current": expected,
        "target": target,
    }:
        reject("HUMAN_AUTH_MISMATCH")
    os.rename(path, path.with_suffix(".consumed"))


def main(argv):
    if os.geteuid() != 0:
        reject("ROOT_ADAPTER_REQUIRED")
    if len(argv) < 2:
        reject("INVALID_ARGUMENTS")
    action, environment = argv[:2]
    if environment not in ("staging", "production", "gateway"):
        reject("INVALID_ENVIRONMENT")
    if action == "status" and len(argv) != 2:
        reject("INVALID_ARGUMENTS")
    if action == "logs":
        if (
            len(argv) != 4
            or argv[2] not in ("api", "worker", "gateway")
            or not argv[3].isdigit()
            or not 20 <= int(argv[3]) <= 500
        ):
            reject("INVALID_ARGUMENTS")
    elif action in ("deploy", "rollback", "backup", "restart"):
        if len(argv) != 5 or environment == "gateway" or not SHA.fullmatch(argv[2]):
            reject("INVALID_ARGUMENTS")
        target = argv[3]
        if action in ("deploy", "rollback") and not SHA.fullmatch(target):
            reject("INVALID_TARGET")
        if action == "restart" and target not in ("api", "worker", "all"):
            reject("INVALID_TARGET")
        if action == "backup" and target != "-":
            reject("INVALID_TARGET")
        if argv[4] != "-" and not re.fullmatch("[0-9a-f]{32}", argv[4]):
            reject("INVALID_APPROVAL")
    elif action != "status":
        reject("INVALID_ACTION")
    config = load(CONFIG)
    if action == "logs":
        target = argv[2]
        if environment == "gateway":
            if target != "gateway":
                reject("INVALID_TARGET")
            unit = config["gateway_unit"]
        else:
            if target == "gateway":
                reject("INVALID_TARGET")
            unit = config["environments"][environment]["units"][target]
        # Per-line limit as well as line count; avoid unbounded journal messages.
        proc = subprocess.Popen(
            ["/usr/bin/journalctl", "-u", unit, "-n", argv[3], "--no-pager", "--output=cat"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        data = proc.stdout.read(65537)
        proc.terminate()
        proc.wait(timeout=5)
        text = data[:65536].decode(errors="replace")
        text = re.sub(r"(?i)(postgres(?:ql)?(?:\+\w+)?://)[^\s]+", r"\1[REDACTED]", text)
        text = re.sub(
            r"(?i)(password|secret|token|api[_-]?key|authorization)\s*[:=]\s*[^\n,;]+",
            r"\1=[REDACTED]",
            text,
        )
        return {"environment": environment, "output": text}
    if environment == "gateway":
        reject("INVALID_ENVIRONMENT")
    binding = config["environments"][environment]
    if action == "status":
        return {
            "environment": environment,
            "current_sha": current(binding),
            "units": {
                k: run(
                    ["/usr/bin/systemctl", "show", v, "--property=ActiveState,MainPID", "--value"]
                )
                for k, v in binding["units"].items()
            },
            "schema_policy": "NO_SCHEMA_CHANGE",
        }
    with open("/run/lock/deepaha-ops-" + environment + ".lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            reject("ENVIRONMENT_BUSY")
        expected, target, approval = argv[2:]
        old = current(binding)
        if old != expected:
            reject("STALE_EXPECTED_CURRENT")
        if not config["mutations_enabled"] or not binding["mutations_enabled"]:
            reject("MUTATIONS_DISABLED")
        host_event(
            "requested",
            {"action": action, "environment": environment, "expected": expected, "target": target},
        )
        if environment == "production":
            receipt(approval, action, environment, expected, target)
        if action == "backup":
            result = backup(binding, old)
            healthy(binding)
            return done(result)
        if action == "restart":
            service(binding, "restart", target)
            healthy(binding)
            return done({"environment": environment, "current_sha": old, "restarted": target})
        directory = release(binding, target, old, environment)
        history_path = REGISTRY / (environment + "-history.json")
        history = load(history_path)
        if action == "rollback" and target not in history:
            reject("NOT_A_VALID_HISTORY_TARGET")
        previous = Path(binding["current"]).resolve()
        service(binding, "stop")
        try:
            switch(binding, directory)
            service(binding, "start")
            healthy(binding)
        except Exception:
            service(binding, "stop")
            switch(binding, previous)
            service(binding, "start")
            healthy(binding)
            reject("DEPLOY_FAILED_APPLICATION_RESTORED_NO_DATABASE_RESTORE")
        if target not in history:
            history.append(target)
        temp = history_path.with_suffix(".tmp")
        temp.write_text(json.dumps(history))
        os.replace(temp, history_path)
        return done(
            {
                "environment": environment,
                "previous_sha": old,
                "current_sha": target,
                "schema_policy": "NO_SCHEMA_CHANGE",
            }
        )


if __name__ == "__main__":
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: reject("INTERRUPTED_RECONCILE_REQUIRED"))
    try:
        print(json.dumps(main(sys.argv[1:]), sort_keys=True))
    except Exception as exc:
        # Do not leak command arguments, connection strings or exception contents.
        code = (
            str(exc)
            if isinstance(exc, RuntimeError) and re.fullmatch("[A-Z_]+", str(exc))
            else "ADAPTER_FAILED"
        )
        print(json.dumps({"error": code}))
        sys.exit(
            1 if isinstance(exc, RuntimeError) and code != "INTERRUPTED_RECONCILE_REQUIRED" else 125
        )
