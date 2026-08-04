from scripts.apply_boundary_jump_cuts import (
    compute_boundary_trim,
    parse_silence_intervals,
    retime_subtitles,
    shift_beep_ranges,
)


def test_parse_silence_intervals_handles_open_tail() -> None:
    stderr = """
[silencedetect @ 0x1] silence_start: 0
[silencedetect @ 0x1] silence_end: 0.42 | silence_duration: 0.42
[silencedetect @ 0x1] silence_start: 9.6
"""
    assert parse_silence_intervals(stderr, duration=10.0) == [
        (0.0, 0.42),
        (9.6, 10.0),
    ]


def test_boundary_trim_keeps_point_one_second_handles() -> None:
    start, end = compute_boundary_trim(
        10.0,
        [(0.0, 0.5), (9.4, 10.0)],
    )
    assert start == 0.4
    assert end == 9.5


def test_internal_silence_is_not_cut() -> None:
    assert compute_boundary_trim(10.0, [(4.0, 5.0)]) == (0.0, 10.0)


def test_fully_silent_asset_is_preserved() -> None:
    assert compute_boundary_trim(10.0, [(0.0, 10.0)]) == (0.0, 10.0)


def test_beep_ranges_shift_with_boundary_cut() -> None:
    ranges = shift_beep_ranges(
        [
            {"id": "a", "startSeconds": 0.2, "endSeconds": 0.7},
            {"id": "b", "startSeconds": 4.0, "endSeconds": 5.0},
        ],
        trim_start=0.4,
        new_duration=4.2,
    )
    assert ranges == [
        {"id": "a", "startSeconds": 0.0, "endSeconds": 0.3},
        {"id": "b", "startSeconds": 3.6, "endSeconds": 4.2},
    ]


def test_subtitles_are_shifted_and_clipped_per_asset() -> None:
    subtitles = [
        {"id": 0, "assetId": "one", "start": 0.2, "end": 0.8, "lines": ["A"]},
        {"id": 1, "assetId": "one", "start": 1.0, "end": 2.0, "lines": ["B"]},
        {"id": 2, "assetId": "two", "start": 5.2, "end": 5.8, "lines": ["C"]},
    ]
    timing = {
        "one": (0.0, 0.0, 0.4, 4.0),
        "two": (5.0, 4.0, 0.1, 3.0),
    }
    shifted = retime_subtitles(subtitles, timing)
    assert shifted == [
        {"id": 0, "assetId": "one", "start": 0.0, "end": 0.4, "lines": ["A"]},
        {"id": 1, "assetId": "one", "start": 0.6, "end": 1.6, "lines": ["B"]},
        {"id": 2, "assetId": "two", "start": 4.1, "end": 4.7, "lines": ["C"]},
    ]
