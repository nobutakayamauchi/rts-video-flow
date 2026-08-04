from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGE_HTML = ROOT / "web_console" / "static" / "manage.html"


class MobileNarrationCaptureMarkupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = MANAGE_HTML.read_text(encoding="utf-8")

    def test_whole_and_range_capture_controls_exist(self) -> None:
        self.assertIn("capturePanel('whole'", self.source)
        self.assertIn("capturePanel('segment'", self.source)
        self.assertIn("navigator.mediaDevices?.getUserMedia", self.source)
        self.assertIn("new MediaRecorder", self.source)

    def test_range_duration_is_checked_before_upload(self) -> None:
        self.assertIn("duration>range+0.25", self.source)
        self.assertIn("残りは無音になります", self.source)

    def test_file_picker_fallback_remains_available(self) -> None:
        self.assertIn('class="narration-file"', self.source)
        self.assertIn('class="segment-file"', self.source)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for syntax check")
    def test_inline_javascript_parses(self) -> None:
        match = re.search(r"<script>(.*)</script>", self.source, flags=re.DOTALL)
        self.assertIsNotNone(match)
        assert match is not None
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "manage.js"
            script.write_text(match.group(1), encoding="utf-8")
            subprocess.run(
                ["node", "--check", str(script)],
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()
