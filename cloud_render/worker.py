from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from google.cloud import storage

ALLOWED_BUCKET = "rts-vlog-render-files-20260805"
ALLOWED_INPUT_PREFIX = "inputs/"
ALLOWED_MANIFEST_PREFIX = "manifests/"
ALLOWED_OUTPUT_PREFIX = "outputs/"
ALLOWED_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".png", ".jpg", ".jpeg"}
MAX_INPUT_BYTES = 512 * 1024 * 1024
MAX_INPUTS = 32
PROBE_TIMEOUT_SECONDS = 30
RENDER_TIMEOUT_SECONDS = 600


def split_gs_uri(uri: str, *, prefix: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    object_name = parsed.path.lstrip("/")
    if parsed.scheme != "gs" or parsed.netloc != ALLOWED_BUCKET or not object_name.startswith(prefix):
        raise ValueError(f"GCS URI is outside the approved boundary: {uri}")
    if ".." in Path(object_name).parts:
        raise ValueError("path traversal is not permitted")
    return parsed.netloc, object_name


def download(client: storage.Client, uri: str, target: Path, *, prefix: str) -> None:
    bucket_name, object_name = split_gs_uri(uri, prefix=prefix)
    target.parent.mkdir(parents=True, exist_ok=True)
    client.bucket(bucket_name).blob(object_name).download_to_filename(target)


def upload(client: storage.Client, source: Path, uri: str) -> None:
    bucket_name, object_name = split_gs_uri(uri, prefix=ALLOWED_OUTPUT_PREFIX)
    client.bucket(bucket_name).blob(object_name).upload_from_filename(source, if_generation_match=0)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,avg_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=PROBE_TIMEOUT_SECONDS,
    )
    return json.loads(completed.stdout)


def verify_downloaded_input(path: Path, expected_hash: str) -> None:
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise SystemExit("input suffix is not allowlisted")
    size = path.stat().st_size
    if not 0 < size <= MAX_INPUT_BYTES:
        raise SystemExit("input size outside security limit")
    if sha256_file(path) != expected_hash:
        raise SystemExit("input hash differs from SECURITY_PASS")
    metadata = probe(path)
    streams = metadata.get("streams") or []
    if not 1 <= len(streams) <= 4:
        raise SystemExit("stream count outside security limit")
    if any(stream.get("codec_type") not in {"video", "audio"} for stream in streams):
        raise SystemExit("active, attachment, subtitle, data, or unknown stream rejected")
    if len([stream for stream in streams if stream.get("codec_type") == "video"]) != 1:
        raise SystemExit("exactly one video/image stream is required")


def validate_manifest(manifest: dict[str, Any], approval_id: str) -> tuple[list[str], list[str], str]:
    if manifest.get("approval_id") != approval_id:
        raise SystemExit("approval id mismatch")
    if manifest.get("security_policy") != "rts-media-security-gate-v1":
        raise SystemExit("security policy mismatch")
    if len(str(manifest.get("security_fingerprint") or "")) != 64:
        raise SystemExit("security fingerprint missing")
    if manifest.get("task_count", 1) != 1:
        raise SystemExit("only one render task is permitted")

    inputs = manifest.get("inputs") or []
    hashes = manifest.get("input_hashes") or []
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= MAX_INPUTS:
        raise SystemExit("inputs must contain 1..32 objects")
    if not isinstance(hashes, list) or len(hashes) != len(inputs):
        raise SystemExit("input hash list mismatch")
    if any(len(str(value)) != 64 for value in hashes):
        raise SystemExit("invalid input hash")
    output_uri = str(manifest.get("output_uri") or "")
    split_gs_uri(output_uri, prefix=ALLOWED_OUTPUT_PREFIX)
    for uri in inputs:
        split_gs_uri(str(uri), prefix=ALLOWED_INPUT_PREFIX)
    return [str(uri) for uri in inputs], [str(value) for value in hashes], output_uri


def main() -> None:
    manifest_uri = os.environ.get("RENDER_MANIFEST_URI", "").strip()
    approval_id = os.environ.get("COST_APPROVAL_ID", "").strip()
    if not manifest_uri or not approval_id:
        raise SystemExit("RENDER_MANIFEST_URI and COST_APPROVAL_ID are required")
    split_gs_uri(manifest_uri, prefix=ALLOWED_MANIFEST_PREFIX)

    client = storage.Client()
    with tempfile.TemporaryDirectory(prefix="rts-render-") as temp_dir:
        root = Path(temp_dir)
        manifest_path = root / "manifest.json"
        download(client, manifest_uri, manifest_path, prefix=ALLOWED_MANIFEST_PREFIX)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        inputs, expected_hashes, output_uri = validate_manifest(manifest, approval_id)

        local_inputs: list[Path] = []
        for index, (uri, expected_hash) in enumerate(zip(inputs, expected_hashes, strict=True)):
            suffix = Path(urlparse(uri).path).suffix.lower()
            local_path = root / "input" / f"{index:03d}{suffix}"
            download(client, uri, local_path, prefix=ALLOWED_INPUT_PREFIX)
            verify_downloaded_input(local_path, expected_hash)
            local_inputs.append(local_path)

        concat_file = root / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{path.as_posix()}'\n" for path in local_inputs),
            encoding="utf-8",
        )
        output_path = root / "output.mp4"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-nostdin",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            "-threads",
            "1",
            str(output_path),
        ]
        subprocess.run(command, check=True, timeout=RENDER_TIMEOUT_SECONDS)
        upload(client, output_path, output_uri)
        print(
            json.dumps(
                {
                    "status": "completed",
                    "approval_id": approval_id,
                    "security_fingerprint": manifest["security_fingerprint"],
                    "output_uri": output_uri,
                }
            )
        )


if __name__ == "__main__":
    main()
