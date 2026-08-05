from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


MAX_INPUT_BYTES = 512 * 1024 * 1024
MAX_RUNTIME_SECONDS = 900
MAX_DAILY_RUNS = 3
APPROVAL_TTL_SECONDS = 900
SECURITY_PASS_MAX_AGE_SECONDS = 3600


@dataclass(frozen=True)
class Estimate:
    project: str
    region: str
    bucket: str
    job: str
    input_bytes: int
    cpu: int
    memory_gib: int
    timeout_seconds: int
    task_count: int
    estimated_max_yen: int


def validate(estimate: Estimate) -> list[str]:
    errors: list[str] = []
    if estimate.project != "rts-vlog-render":
        errors.append("project mismatch")
    if estimate.region != "asia-northeast1":
        errors.append("region mismatch")
    if estimate.bucket != "rts-vlog-render-files-20260805":
        errors.append("bucket mismatch")
    if estimate.job != "rts-vlog-render":
        errors.append("job mismatch")
    if estimate.task_count != 1:
        errors.append("task_count must be 1")
    if estimate.cpu not in {1, 2}:
        errors.append("cpu must be 1 or 2")
    if not 1 <= estimate.memory_gib <= 4:
        errors.append("memory_gib must be between 1 and 4")
    if not 1 <= estimate.timeout_seconds <= MAX_RUNTIME_SECONDS:
        errors.append("timeout exceeds safe maximum")
    if not 0 < estimate.input_bytes <= MAX_INPUT_BYTES:
        errors.append("input size exceeds safe maximum")
    if estimate.estimated_max_yen < 0:
        errors.append("estimated_max_yen must be non-negative")
    return errors


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def revalidate_security_files(files: list[object]) -> None:
    for item in files:
        if not isinstance(item, dict):
            raise SystemExit("security pass contains invalid file records")
        raw_path = str(item.get("path") or "")
        expected_hash = str(item.get("sha256") or "")
        expected_size = int(item.get("size_bytes") or 0)
        if not raw_path or len(expected_hash) != 64 or expected_size <= 0:
            raise SystemExit("security pass contains invalid file records")

        path = Path(raw_path)
        if not path.is_file() or path.is_symlink():
            raise SystemExit("security pass input file missing or unsafe")
        try:
            actual_size = path.stat().st_size
            actual_hash = sha256_file(path)
        except OSError as exc:
            raise SystemExit("security pass input file cannot be read") from exc
        if actual_size != expected_size:
            raise SystemExit("security pass file size changed")
        if not secrets.compare_digest(actual_hash, expected_hash):
            raise SystemExit("security pass file hash mismatch")


def load_security_pass(path: Path, expected_input_bytes: int) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("valid SECURITY_PASS file is required") from exc
    if payload.get("status") != "PASS":
        raise SystemExit("security gate did not pass")
    if payload.get("policy") != "rts-media-security-gate-v1":
        raise SystemExit("unsupported security policy")
    fingerprint = str(payload.get("security_fingerprint") or "")
    if len(fingerprint) != 64:
        raise SystemExit("security fingerprint missing")
    inspected_at = int(payload.get("inspected_at") or 0)
    now = int(time.time())
    if inspected_at <= 0 or now - inspected_at > SECURITY_PASS_MAX_AGE_SECONDS:
        raise SystemExit("security pass expired")
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise SystemExit("security pass contains no files")
    total_bytes = sum(int(item.get("size_bytes") or 0) for item in files if isinstance(item, dict))
    if total_bytes != expected_input_bytes:
        raise SystemExit("security pass input size mismatch")
    if any(len(str(item.get("sha256") or "")) != 64 for item in files if isinstance(item, dict)):
        raise SystemExit("security pass contains invalid hashes")
    revalidate_security_files(files)
    return payload


def issue_approval(
    estimate: Estimate,
    state_dir: Path,
    security_pass: dict[str, Any],
) -> dict[str, object]:
    state_dir.mkdir(parents=True, exist_ok=True)
    day = time.strftime("%Y-%m-%d", time.gmtime())
    counter_path = state_dir / f"runs-{day}.json"
    count = 0
    if counter_path.exists():
        count = int(json.loads(counter_path.read_text(encoding="utf-8")).get("count", 0))
    if count >= MAX_DAILY_RUNS:
        raise SystemExit("daily paid-test limit reached")

    now = int(time.time())
    payload = asdict(estimate) | {
        "approval_id": secrets.token_urlsafe(18),
        "issued_at": now,
        "expires_at": now + APPROVAL_TTL_SECONDS,
        "single_use": True,
        "security_fingerprint": security_pass["security_fingerprint"],
        "input_hashes": [item["sha256"] for item in security_pass["files"]],
        "security_policy": security_pass["policy"],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    payload["fingerprint"] = hashlib.sha256(canonical).hexdigest()
    approval_path = state_dir / f"approval-{payload['approval_id']}.json"
    approval_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    counter_path.write_text(json.dumps({"count": count + 1}), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a one-shot approval for a potentially paid cloud render.")
    parser.add_argument("--security-pass", required=True, type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--input-bytes", required=True, type=int)
    parser.add_argument("--cpu", type=int, default=1)
    parser.add_argument("--memory-gib", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--task-count", type=int, default=1)
    parser.add_argument("--estimated-max-yen", required=True, type=int)
    parser.add_argument("--state-dir", default="temp/cloud-cost-gate")
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args()

    estimate = Estimate(
        project=args.project,
        region=args.region,
        bucket=args.bucket,
        job=args.job,
        input_bytes=args.input_bytes,
        cpu=args.cpu,
        memory_gib=args.memory_gib,
        timeout_seconds=args.timeout_seconds,
        task_count=args.task_count,
        estimated_max_yen=args.estimated_max_yen,
    )
    errors = validate(estimate)
    security_pass = load_security_pass(args.security_pass, estimate.input_bytes)
    print(
        json.dumps(
            {
                "security": {
                    "status": security_pass["status"],
                    "fingerprint": security_pass["security_fingerprint"],
                    "files": len(security_pass["files"]),
                    "local_hash_revalidated": True,
                },
                "estimate": asdict(estimate),
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if errors:
        raise SystemExit(2)
    if not args.approve:
        raise SystemExit("approval required: inspect the security result and estimate, then rerun with --approve")

    confirmation = input("安全確認と課金可能性を理解し、この1回だけ実行を承認しますか？ [YES]: ").strip()
    if confirmation != "YES":
        raise SystemExit("not approved")
    approval = issue_approval(estimate, Path(args.state_dir), security_pass)
    print(json.dumps({"approved": approval}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
