from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


asset_audio = load_module("prepare_asset_audio", "scripts/prepare_asset_audio.py")
manifest = load_module("build_vlog_manifest", "scripts/build_vlog_manifest.py")
remotion = load_module("prepare_vlog_remotion", "scripts/prepare_vlog_remotion.py")


class NarrationSegmentModelTest(unittest.TestCase):
    def test_segments_are_sorted_and_normalized(self) -> None:
        segments = asset_audio.normalize_narration_segments(
            [
                {"narration": "b.m4a", "startSeconds": 8, "endSeconds": 10},
                {"narration": "a.m4a", "startSeconds": 1.5, "endSeconds": 3},
            ],
            asset_id="asset-001",
            duration=12,
        )
        self.assertEqual([segment["startSeconds"] for segment in segments], [1.5, 8.0])
        self.assertEqual(segments[0]["mode"], "replace")
        self.assertEqual(segments[0]["subtitleMode"], "auto")

    def test_overlapping_segments_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "may not overlap"):
            asset_audio.normalize_narration_segments(
                [
                    {"narration": "a.m4a", "startSeconds": 1, "endSeconds": 4},
                    {"narration": "b.m4a", "startSeconds": 3.5, "endSeconds": 5},
                ],
                asset_id="asset-001",
                duration=10,
            )

    def test_range_must_fit_inside_video(self) -> None:
        with self.assertRaisesRegex(ValueError, "ends after the video"):
            asset_audio.normalize_narration_segments(
                [{"narration": "a.m4a", "startSeconds": 8, "endSeconds": 12}],
                asset_id="asset-001",
                duration=10,
            )

    def test_source_subtitles_inside_replaced_range_are_removed(self) -> None:
        merged: list[dict[str, object]] = []
        asset_audio.append_shifted_subtitles(
            merged,
            [
                {"start": 0.0, "end": 1.0, "lines": ["keep"]},
                {"start": 2.0, "end": 3.0, "lines": ["remove"]},
                {"start": 4.0, "end": 5.0, "lines": ["keep too"]},
            ],
            cursor=10.0,
            asset_id="asset-001",
            source_role="screen-source",
            excluded_ranges=[{"startSeconds": 1.5, "endSeconds": 3.5}],
        )
        self.assertEqual([entry["lines"] for entry in merged], [["keep"], ["keep too"]])
        self.assertEqual(merged[0]["start"], 10.0)
        self.assertEqual(merged[1]["start"], 14.0)

    def test_segment_subtitles_receive_asset_and_local_offsets(self) -> None:
        merged: list[dict[str, object]] = []
        asset_audio.append_shifted_subtitles(
            merged,
            [{"start": 0.2, "end": 1.0, "lines": ["patch"]}],
            cursor=20.0,
            local_offset=6.0,
            asset_id="asset-002",
            source_role="screen-range-narration",
        )
        self.assertEqual(merged[0]["start"], 26.2)
        self.assertEqual(merged[0]["end"], 27.0)
        self.assertEqual(merged[0]["assetId"], "asset-002")


class ManifestSegmentValidationTest(unittest.TestCase):
    def test_manifest_accepts_non_overlapping_video_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "screen").mkdir()
            (project / "narration").mkdir()
            (project / "screen" / "clip.mp4").touch()
            (project / "narration" / "one.m4a").touch()
            (project / "narration" / "two.m4a").touch()
            item = manifest.normalize_item(
                project,
                {
                    "type": "video",
                    "source": "screen/clip.mp4",
                    "audioMode": "source",
                    "narrationSegments": [
                        {
                            "narration": "narration/two.m4a",
                            "startSeconds": 5,
                            "endSeconds": 7,
                        },
                        {
                            "narration": "narration/one.m4a",
                            "startSeconds": 1,
                            "endSeconds": 2,
                        },
                    ],
                },
                0,
            )
            self.assertEqual(
                [segment["startSeconds"] for segment in item["narrationSegments"]],
                [1.0, 5.0],
            )

    def test_manifest_rejects_segments_on_images(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "screenshots").mkdir()
            (project / "narration").mkdir()
            (project / "screenshots" / "shot.png").touch()
            (project / "narration" / "one.m4a").touch()
            with self.assertRaisesRegex(ValueError, "only supports video"):
                manifest.normalize_item(
                    project,
                    {
                        "type": "image",
                        "source": "screenshots/shot.png",
                        "narrationSegments": [
                            {
                                "narration": "narration/one.m4a",
                                "startSeconds": 1,
                                "endSeconds": 2,
                            }
                        ],
                    },
                    0,
                )


class RemotionSegmentPreparationTest(unittest.TestCase):
    def test_build_copies_segment_audio_and_emits_range(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            public = root / "public"
            (project / "screen").mkdir(parents=True)
            (project / "narration").mkdir()
            (project / "screen" / "clip.mp4").write_bytes(b"video")
            (project / "narration" / "patch.m4a").write_bytes(b"audio")
            payload = {
                "timeline": [
                    {
                        "id": "asset-001",
                        "type": "video",
                        "role": "screen",
                        "source": "screen/clip.mp4",
                        "resolvedDuration": 10,
                        "audioMode": "source",
                        "narrationSegments": [
                            {
                                "id": "patch-1",
                                "startSeconds": 2,
                                "endSeconds": 4.5,
                                "mode": "replace",
                                "narration": "narration/patch.m4a",
                            }
                        ],
                    }
                ]
            }
            timeline, total = remotion.build(project, payload, public)
            self.assertEqual(total, 10)
            self.assertEqual(timeline[0]["narrationSegments"][0]["start"], 2.0)
            self.assertEqual(timeline[0]["narrationSegments"][0]["duration"], 2.5)
            self.assertTrue(
                (public / timeline[0]["narrationSegments"][0]["narration"]).is_file()
            )


if __name__ == "__main__":
    unittest.main()
