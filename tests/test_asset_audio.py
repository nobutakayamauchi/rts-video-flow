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


class AssetAudioDefaultsTest(unittest.TestCase):
    def test_video_defaults_to_source_audio(self) -> None:
        self.assertEqual(asset_audio.default_audio_mode({}, "video"), "source")
        self.assertEqual(asset_audio.default_subtitle_mode({}, "source"), "auto")

    def test_image_defaults_to_mute(self) -> None:
        self.assertEqual(asset_audio.default_audio_mode({}, "image"), "mute")
        self.assertEqual(asset_audio.default_subtitle_mode({}, "mute"), "none")

    def test_narration_path_defaults_to_narration_mode(self) -> None:
        item = {"narration": "narration/asset.m4a"}
        self.assertEqual(asset_audio.default_audio_mode(item, "video"), "narration")

    def test_subtitles_are_shifted_to_global_timeline(self) -> None:
        merged: list[dict[str, object]] = []
        asset_audio.append_shifted_subtitles(
            merged,
            [{"start": 0.25, "end": 1.5, "lines": ["hello"]}],
            cursor=10.0,
            asset_id="asset-002",
            source_role="screen-narration",
        )
        self.assertEqual(merged[0]["start"], 10.25)
        self.assertEqual(merged[0]["end"], 11.5)
        self.assertEqual(merged[0]["assetId"], "asset-002")
        self.assertEqual(merged[0]["sourceRole"], "screen-narration")


class ManifestNormalizationTest(unittest.TestCase):
    def test_legacy_video_and_image_receive_stable_audio_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "camera").mkdir()
            (project / "screenshots").mkdir()
            (project / "camera" / "clip.mp4").touch()
            (project / "screenshots" / "shot.png").touch()

            video = manifest.normalize_item(
                project,
                {"type": "video", "source": "camera/clip.mp4", "role": "camera"},
                0,
            )
            image = manifest.normalize_item(
                project,
                {"type": "image", "source": "screenshots/shot.png", "role": "screenshot"},
                1,
            )

            self.assertEqual(video["id"], "asset-001")
            self.assertEqual(video["audioMode"], "source")
            self.assertEqual(video["subtitleMode"], "auto")
            self.assertEqual(image["id"], "asset-002")
            self.assertEqual(image["audioMode"], "mute")
            self.assertEqual(image["subtitleMode"], "none")
            self.assertEqual(image["durationSeconds"], 5.0)

    def test_narrated_asset_is_normalized_to_narration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "screen").mkdir()
            (project / "narration").mkdir()
            (project / "screen" / "clip.mp4").touch()
            (project / "narration" / "clip.m4a").touch()

            item = manifest.normalize_item(
                project,
                {
                    "type": "video",
                    "source": "screen/clip.mp4",
                    "narration": "narration/clip.m4a",
                },
                0,
            )

            self.assertEqual(item["audioMode"], "narration")
            self.assertEqual(item["subtitleMode"], "auto")


if __name__ == "__main__":
    unittest.main()
