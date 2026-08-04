import math

from scripts.audit_high_frequency_audio import (
    Candidate,
    WindowLevel,
    detect_candidates,
    merge_overlapping,
    parse_astats,
)


def test_parse_astats_reads_window_time_and_rms() -> None:
    text = """
frame:0 pts:0 pts_time:0
lavfi.astats.Overall.RMS_level=-12.5
frame:1 pts:4800 pts_time:0.1
lavfi.astats.Overall.RMS_level=-inf
"""
    values = parse_astats(text)
    assert values[0] == WindowLevel(0.0, -12.5)
    assert values[1].time_seconds == 0.1
    assert math.isinf(values[1].rms_db) and values[1].rms_db < 0


def test_detects_only_sustained_loud_dominant_band() -> None:
    full = [WindowLevel(i / 10, -20.0) for i in range(8)]
    band = [
        WindowLevel(0.0, -40.0),
        WindowLevel(0.1, -21.0),
        WindowLevel(0.2, -20.0),
        WindowLevel(0.3, -19.0),
        WindowLevel(0.4, -40.0),
        WindowLevel(0.5, -40.0),
        WindowLevel(0.6, -40.0),
        WindowLevel(0.7, -40.0),
    ]
    candidates = detect_candidates(
        full,
        band,
        center_hz=17000,
        min_rms_db=-24.0,
        dominance_db=6.0,
        min_run_seconds=0.3,
    )
    assert len(candidates) == 1
    assert candidates[0].center_hz == 17000
    assert candidates[0].start_seconds == 0.1
    assert candidates[0].end_seconds == 0.4


def test_short_high_frequency_burst_is_not_reported() -> None:
    full = [WindowLevel(i / 10, -20.0) for i in range(5)]
    band = [
        WindowLevel(0.0, -20.0),
        WindowLevel(0.1, -20.0),
        WindowLevel(0.2, -40.0),
        WindowLevel(0.3, -40.0),
        WindowLevel(0.4, -40.0),
    ]
    assert not detect_candidates(
        full,
        band,
        center_hz=17500,
        min_rms_db=-24.0,
        dominance_db=6.0,
        min_run_seconds=0.3,
    )


def test_neighbouring_scan_bands_merge_one_tone() -> None:
    candidates = [
        Candidate(16500, 1.0, 2.0, 1.0, -18.0, 2.0),
        Candidate(17000, 1.1, 2.1, 1.0, -16.0, 4.0),
    ]
    merged = merge_overlapping(candidates)
    assert len(merged) == 1
    assert merged[0].center_hz == 17000
    assert merged[0].start_seconds == 1.0
    assert merged[0].end_seconds == 2.1
