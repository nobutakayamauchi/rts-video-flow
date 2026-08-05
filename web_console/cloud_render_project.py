#!/usr/bin/env python3
"""Prepare one Vlog project for governed Cloud Run rendering.

This module performs bounded local inspection, input normalization, and GCS
upload only. It never consumes approval and never starts Cloud Run. The
returned handoff remains in AWAITING_APPROVAL until the separate approval
endpoint is called.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from scripts.media_security_gate import create_security_pass
from web_console.app import ROOT, load_plan, resolve_project_file, safe_project_name
from web_console.app_v3 import ensure_required_roles, require_project_path
from web_console.cloud_render_handoff import HandoffError, HandoffStore, RenderPolicy, SecurityBinding

STAGING_ROOT = ROOT / "state" / "cloud-render-staging"
ALLOWED_INPUT_STREAMS = {"video", "audio"}


@dataclass(frozen=True)
class PreparedProject:
    record: dict[str, Any]
    security_pass: dict[str, Any]
    manifest: dict[str, Any]
    staging_dir: Path


def collect_timeline_sources(project_name: str) -> tuple[Path, list[Path]]:
    project_path = require_project_path(project_name)
    plan = load_plan(project_path)
    ensure_required_roles(plan)
    sources: list[Path] = []
    seen: set[Path] = set()
    for item in plan.get("timeline", []):
        if not isinstance(item, dict):
            continue
        source = resolve_project_file(project_path, item.get("source"))
        if source is None or not source.is_file():
            raise HandoffError(f"timeline source is missing: {item.get('id', 'unknown')}")
        resolved = source.resolve()
        if resolved not in seen:
            seen.add(resolved)
            sources.append(resolved)
    if not sources:
        raise HandoffError("project has no renderable timeline sources")
    if len(sources) > 32:
        raise HandoffError("project contains more than 32 render inputs")
    return project_path, sources


def inspect_streams(
    source: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[dict[str, Any]]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=index,codec_type,codec_name",
        "-of",
        "json",
        str(source),
    ]
    try:
        result = runner(command, check=True, capture_output=True, text=True, timeout=60)
        payload = json.loads(result.stdout or "{}")
    except subprocess.TimeoutExpired as error:
        raise HandoffError(f"media inspection timed out: {source.name}") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "ffprobe failed").strip()
        raise HandoffError(f"media inspection failed for {source.name}: {detail[-1000:]}") from error
    except (json.JSONDecodeError, TypeError) as error:
        raise HandoffError(f"invalid ffprobe response for {source.name}") from error
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise HandoffError(f"media inspection returned no stream list: {source.name}")
    return [stream for stream in streams if isinstance(stream, dict)]


def _stream_summary(streams: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for stream in streams:
        kind = str(stream.get("codec_type") or "unknown")
        summary[kind] = summary.get(kind, 0) + 1
    return summary


def normalize_cloud_input(
    source: Path,
    target: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Create one governed staging copy without mutating the source.

    Inputs already containing exactly one video stream, at most one audio
    stream, and no auxiliary stream are copied byte-for-byte. Other supported
    inputs are remuxed to MP4 while selecting only the first video and optional
    first audio stream. Re-encoding is never performed implicitly.
    """

    before = inspect_streams(source, runner=runner)
    before_summary = _stream_summary(before)
    video_count = before_summary.get("video", 0)
    audio_count = before_summary.get("audio", 0)
    unsupported = sorted(set(before_summary) - ALLOWED_INPUT_STREAMS)

    if video_count != 1:
        raise HandoffError(f"cloud input must contain exactly one video stream: {source.name}")

    passthrough = audio_count <= 1 and not unsupported and len(before) <= 2
    if passthrough:
        target = target.with_suffix(source.suffix.lower() or ".mp4")
        shutil.copy2(source, target)
        method = "passthrough"
    else:
        target = target.with_suffix(".mp4")
        command = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c",
            "copy",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-movflags",
            "+faststart",
            str(target),
        ]
        try:
            runner(command, check=True, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired as error:
            target.unlink(missing_ok=True)
            raise HandoffError(f"cloud input normalization timed out: {source.name}") from error
        except subprocess.CalledProcessError as error:
            target.unlink(missing_ok=True)
            detail = (error.stderr or error.stdout or "ffmpeg remux failed").strip()
            raise HandoffError(f"cloud input normalization failed for {source.name}: {detail[-1500:]}") from error
        method = "remux"

    after = inspect_streams(target, runner=runner)
    after_summary = _stream_summary(after)
    if after_summary.get("video", 0) != 1:
        target.unlink(missing_ok=True)
        raise HandoffError(f"normalized input does not contain exactly one video stream: {source.name}")
    if after_summary.get("audio", 0) > 1:
        target.unlink(missing_ok=True)
        raise HandoffError(f"normalized input contains more than one audio stream: {source.name}")
    forbidden_after = sorted(set(after_summary) - ALLOWED_INPUT_STREAMS)
    if forbidden_after:
        target.unlink(missing_ok=True)
        raise HandoffError(
            f"normalized input still contains forbidden streams ({', '.join(forbidden_after)}): {source.name}"
        )

    return {
        "source": str(source),
        "staged": str(target),
        "method": method,
        "before": before_summary,
        "after": after_summary,
        "removed_streams": max(0, len(before) - len(after)),
    }


def stage_ascii_inputs(
    project_name: str,
    sources: list[Path],
    run_id: str,
    *,
    media_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[Path, list[Path]]:
    stage = STAGING_ROOT / safe_project_name(project_name) / run_id
    inputs_dir = stage / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=False)
    staged: list[Path] = []
    report: list[dict[str, Any]] = []
    try:
        for index, source in enumerate(sources, start=1):
            base_target = inputs_dir / f"input-{index:03d}"
            item = normalize_cloud_input(source, base_target, runner=media_runner)
            target = Path(str(item["staged"]))
            staged.append(target)
            report.append(item)
        (stage / "NORMALIZATION_REPORT.json").write_text(
            json.dumps({"version": 1, "inputs": report}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return stage, staged
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _run(command: list[str], *, runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    try:
        runner(command, check=True, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as error:
        raise HandoffError("GCS upload timed out") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "GCS upload failed").strip()
        raise HandoffError(detail[-2000:]) from error


def prepare_project(
    store: HandoffStore,
    project_name: str,
    mode: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    media_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    now: int | None = None,
) -> PreparedProject:
    policy = RenderPolicy()
    current = int(time.time() if now is None else now)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(current)) + f"-{safe_project_name(project_name)}"
    _, sources = collect_timeline_sources(project_name)
    stage, staged = stage_ascii_inputs(project_name, sources, run_id, media_runner=media_runner)

    try:
        security_pass = create_security_pass(staged)
        files = security_pass.get("files") or []
        hashes = tuple(str(item["sha256"]) for item in files)
        fingerprint = str(security_pass["security_fingerprint"])
        input_uris = [f"gs://{policy.bucket}/inputs/{run_id}/{path.name}" for path in staged]
        manifest_uri = f"gs://{policy.bucket}/manifests/{run_id}.json"
        output_uri = f"gs://{policy.bucket}/outputs/{run_id}/output.mp4"

        for path, uri in zip(staged, input_uris, strict=True):
            _run(["gcloud", "storage", "cp", str(path), uri, "--quiet"], runner=runner)

        record = store.create_pending(
            project=project_name,
            mode=mode,
            manifest_uri=manifest_uri,
            output_uri=output_uri,
            security=SecurityBinding(
                policy=str(security_pass["policy"]),
                fingerprint=fingerprint,
                input_hashes=hashes,
                files=len(hashes),
            ),
            policy=policy,
            now=current,
        )
        manifest = {
            "version": 1,
            "approval_id": record["request_id"],
            "project": project_name,
            "mode": mode,
            "task_count": 1,
            "inputs": input_uris,
            "input_hashes": list(hashes),
            "security_policy": security_pass["policy"],
            "security_fingerprint": fingerprint,
            "output_uri": output_uri,
        }
        manifest_path = stage / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            _run(["gcloud", "storage", "cp", str(manifest_path), manifest_uri, "--quiet"], runner=runner)
        except Exception:
            store.path_for(record["request_id"]).unlink(missing_ok=True)
            raise
        (stage / "SECURITY_PASS.json").write_text(
            json.dumps(security_pass, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return PreparedProject(record=record, security_pass=security_pass, manifest=manifest, staging_dir=stage)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
