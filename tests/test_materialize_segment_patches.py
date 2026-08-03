from __future__ import annotations

import array
import importlib.util
import math
import shutil
import subprocess
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


patches = load_module(
    "materialize_segment_patches", "scripts/materialize_segment_patches.py"
)


class FilterGraphTest(unittest.TestCase):
    def test_filter_graph_mutes_range_and_delays_patch(self) -> None:
        graph = patches.build_filter_graph(
            duration=6.0,
            base_input_index=0,
            segment_input_indexes=[1],
            segments=[{"startSeconds": 2.0, "endSeconds": 4.0}],
        )
        self.assertIn("volume=0:enable='between(t,2,4)'", graph)
        self.assertIn("adelay=2000|2000", graph)
        self.assertIn("amix=inputs=2", graph)


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "ffmpeg and ffprobe are required",
)
class EncodedAudioIntegrationTest(unittest.TestCase):
    def run_command(self, command: list[str]) -> None:
        subprocess.run(command, check=True, capture_output=True, text=True)

    def estimate_frequency(
        self, media: Path, *, start: float, duration: float = 0.5
    ) -> float:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(start),
                "-t",
                str(duration),
                "-i",
                str(media),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-f",
                "s16le",
                "-",
            ],
            check=True,
            capture_output=True,
        )
        samples = array.array("h")
        samples.frombytes(result.stdout)
        if not samples:
            self.fail("No decoded samples")
        crossings = 0
        previous = samples[0]
        for current in samples[1:]:
            if (previous < 0 <= current) or (previous >= 0 > current):
                crossings += 1
            previous = current
        return crossings / (2.0 * duration)

    def test_materialized_video_contains_patch_only_inside_range(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            output_dir = Path(temporary) / "output"
            (project / "camera").mkdir(parents=True)
            (project / "narration" / "segments").mkdir(parents=True)
            source = project / "camera" / "source.mp4"
            narration = project / "narration" / "segments" / "patch.m4a"

            self.run_command(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=160x90:r=10:d=4",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:sample_rate=48000:duration=4",
                    "-shortest",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    str(source),
                ]
            )
            self.run_command(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=880:sample_rate=48000:duration=1",
                    "-c:a",
                    "aac",
                    str(narration),
                ]
            )

            item = {
                "id": "asset-test",
                "type": "video",
                "source": "camera/source.mp4",
                "audioMode": "source",
                "resolvedDuration": 4.0,
                "narrationSegments": [
                    {
                        "id": "segment-test",
                        "startSeconds": 1.0,
                        "endSeconds": 2.0,
                        "mode": "replace",
                        "narration": "narration/segments/patch.m4a",
                    }
                ],
            }
            rendered = patches.materialize_video(
                project=project,
                item=item,
                index=0,
                output_dir=output_dir,
            )
            self.assertIsNotNone(rendered)
            assert rendered is not None

            before = self.estimate_frequency(rendered, start=0.2)
            inside = self.estimate_frequency(rendered, start=1.2)
            after = self.estimate_frequency(rendered, start=2.4)

            self.assertTrue(math.isclose(before, 440, rel_tol=0.12), before)
            self.assertTrue(math.isclose(inside, 880, rel_tol=0.12), inside)
            self.assertTrue(math.isclose(after, 440, rel_tol=0.12), after)


if __name__ == "__main__":
    unittest.main()
