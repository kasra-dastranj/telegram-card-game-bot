"""Actions client: send one verified archive to the forced SSH command."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from package_release import verify


def main():
    operation = os.environ["OPERATION"]
    header = {"operation": operation, "run_id": os.environ["GITHUB_RUN_ID"],
              "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"]}
    payload = b""
    if operation == "deploy":
        archive = Path("release-artifact/telbattle-release.tar.gz")
        verify(archive, os.environ["GITHUB_SHA"], header["run_id"])
        payload = archive.read_bytes()
        checksum = hashlib.sha256(payload).hexdigest()
        if checksum != Path("release-artifact/telbattle-release.sha256").read_text().strip():
            raise RuntimeError("artifact checksum mismatch")
        header.update(source_sha=os.environ["GITHUB_SHA"], archive_sha256=checksum)
    elif operation == "rollback":
        header["expected_current_sha"] = os.environ["ROLLBACK_FROM_SHA"]
    else:
        raise RuntimeError("invalid operation")
    host, user = os.environ["DEPLOY_HOST"], os.environ["DEPLOY_USER"]
    port = os.environ["DEPLOY_PORT"] or "22"
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host) or user != "telbattle-deploy" or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise RuntimeError("invalid deployment connection configuration")
    key, known = os.environ["DEPLOY_SSH_PRIVATE_KEY"], os.environ["DEPLOY_KNOWN_HOSTS"]
    if not key.strip() or not known.strip():
        raise RuntimeError("production SSH secrets are not configured")
    with tempfile.TemporaryDirectory() as directory:
        identity, hosts = Path(directory) / "key", Path(directory) / "known_hosts"
        identity.write_text(key + "\n", encoding="utf-8")
        identity.chmod(0o600)
        hosts.write_text(known + "\n", encoding="utf-8")
        hosts.chmod(0o600)
        env = {k: v for k, v in os.environ.items() if k not in {"DEPLOY_SSH_PRIVATE_KEY", "DEPLOY_KNOWN_HOSTS"}}
        result = subprocess.run(["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                                 "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=20",
                                 "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
                                 "-o", "UserKnownHostsFile=" + str(hosts), "-i", str(identity),
                                 "-p", port, user + "@" + host, "telbattle-deploy"],
                                input=json.dumps(header).encode("utf-8") + b"\n" + payload,
                                capture_output=True, timeout=600, env=env)
    # The trusted server emits metadata only. Never forward SSH stderr or arbitrary service output.
    try:
        receipt = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError("SSH deployment failed before a receipt; owner should check server logs") from None
    safe_keys = {"status", "operation", "source_sha", "previous_sha", "release", "backup", "run_id", "internal_health", "error"}
    if not isinstance(receipt, dict) or set(receipt) - safe_keys:
        raise RuntimeError("invalid server receipt")
    if receipt.get("status") == "ok" and (receipt.get("run_id") != header["run_id"] or
            (operation == "deploy" and receipt.get("source_sha") != header["source_sha"])):
        raise RuntimeError("server receipt identity differs from the tested release")
    Path("deployment-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write("Internal deployment receipt\n\n```json\n" + json.dumps(receipt, indent=2) + "\n```\n")
    print(json.dumps(receipt))
    if result.returncode or receipt.get("status") != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
