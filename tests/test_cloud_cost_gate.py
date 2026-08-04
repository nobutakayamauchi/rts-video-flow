from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "cloud_cost_gate.py"
spec = importlib.util.spec_from_file_location("cloud_cost_gate", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
Estimate = module.Estimate
validate = module.validate


def valid_estimate() -> Estimate:
    return Estimate(
        project="rts-vlog-render",
        region="asia-northeast1",
        bucket="rts-vlog-render-files-20260805",
        job="rts-vlog-render",
        input_bytes=10_000_000,
        cpu=2,
        memory_gib=4,
        timeout_seconds=600,
        task_count=1,
        estimated_max_yen=10,
    )


def test_valid_estimate_passes() -> None:
    assert validate(valid_estimate()) == []


def test_rejects_parallel_tasks() -> None:
    estimate = Estimate(**(valid_estimate().__dict__ | {"task_count": 2}))
    assert "task_count must be 1" in validate(estimate)


def test_rejects_wrong_project_and_region() -> None:
    estimate = Estimate(**(valid_estimate().__dict__ | {"project": "wrong", "region": "us-central1"}))
    errors = validate(estimate)
    assert "project mismatch" in errors
    assert "region mismatch" in errors


def test_rejects_oversized_input() -> None:
    estimate = Estimate(**(valid_estimate().__dict__ | {"input_bytes": module.MAX_INPUT_BYTES + 1}))
    assert "input size exceeds safe maximum" in validate(estimate)
