from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRITEOUT_HTML = ROOT / "web_console" / "static" / "writeout.html"


class WriteoutPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WRITEOUT_HTML.read_text(encoding="utf-8")

    def test_writeout_controls_exist(self) -> None:
        self.assertIn('id="render"', self.source)
        self.assertIn('id="download"', self.source)
        self.assertIn("api/compile", self.source)
        self.assertIn("api/download/", self.source)

    def test_project_query_is_restored(self) -> None:
        self.assertIn("new URLSearchParams(location.search)", self.source)
        self.assertIn("params.get('project')", self.source)

    def test_automatic_publication_is_not_added(self) -> None:
        self.assertNotIn("youtube", self.source.lower())
        self.assertNotIn("publish", self.source.lower())

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for syntax check")
    def test_inline_javascript_parses(self) -> None:
        match = re.search(r"<script>(.*)</script>", self.source, flags=re.DOTALL)
        self.assertIsNotNone(match)
        assert match is not None
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "writeout.js"
            script.write_text(match.group(1), encoding="utf-8")
            subprocess.run(
                ["node", "--check", str(script)],
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()
