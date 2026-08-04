from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from google.cloud import storage


def split_gs_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError(f"invalid gs uri: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def download(client: storage.Client, uri: str, target: Path) -> None:
    bucket_name, object_name = split_gs_uri(uri)
    target.parent.mkdir(parents=True, exist_ok=True)
    client.bucket(bucket_name).blob(object_name).download_to_filename(target)


def upload(client: storage.Client, source: Path, uri: str) -> None:
    bucket_name, object_name = split_gs_uri(uri)
    client.bucket(bucket_name).blob(object_name).upload_from_filename(source)


def main() -> None:
    manifest_uri = os.environ.get("RENDER_MANIFEST_URI", "").strip()
    approval_id = os.environ.get("COST_APPROVAL_ID", "").strip()
    if not manifest_uri or not approval_id:
        raise SystemExit("RENDER_MANIFEST_URI and COST_APPROVAL_ID are required")

    client = storage.Client()
    with tempfile.TemporaryDirectory(prefix="rts-render-") as temp_dir:
        root = Path(temp_dir)
        manifest_path = root / "manifest.json"
        download(client, manifest_uri, manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        if manifest.get("approval_id") != approval_id:
            raise SystemExit("approval id mismatch")
        if manifest.get("task_count", 1) != 1:
            raise SystemExit("only one render task is permitted")

        inputs = manifest.get("inputs") or []
        if not inputs or len(inputs) > 32:
            raise SystemExit("inputs must contain 1..32 objects")

        local_inputs: list[Path] = []
        for index, uri in enumerate(inputs):
            suffix = Path(urlparse(uri).path).suffix or ".mp4"
            local_path = root / "input" / f"{index:03d}{suffix}"
            download(client, uri, local_path)
            local_inputs.append(local_path)

        concat_file = root / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{path.as_posix()}'\n" for path in local_inputs),
            encoding="utf-8",
        )
        output_path = root / "output.mp4"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            "-threads", "2", str(output_path),
        ]
        subprocess.run(command, check=True)
        upload(client, output_path, manifest["output_uri"])
        print(json.dumps({"status": "completed", "approval_id": approval_id, "output_uri": manifest["output_uri"]}))


if __name__ == "__main__":
    main()
