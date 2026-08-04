from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import web_console.app as base
import web_console.app_v3 as v3


ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    ROOT / "web_console" / "static" / "compose.html",
    ROOT / "web_console" / "static" / "material.html",
    ROOT / "web_console" / "static" / "output.html",
    ROOT / "web_console" / "static" / "trash.html",
]


class CompositionMarkupTest(unittest.TestCase):
    def test_required_pages_and_actions_exist(self) -> None:
        compose = PAGES[0].read_text(encoding="utf-8")
        output = PAGES[2].read_text(encoding="utf-8")
        trash = PAGES[3].read_text(encoding="utf-8")

        for label in ("オープニング", "本編", "エンディング", "変更を反映"):
            self.assertIn(label, compose)
        self.assertIn("このカットの生成物だけ削除", output)
        self.assertIn("生成物をすべて削除", output)
        self.assertIn("元に戻す", trash)
        self.assertIn("ゴミ箱を空にする", trash)

    def test_no_automatic_publication_is_added(self) -> None:
        combined = "\n".join(path.read_text(encoding="utf-8") for path in PAGES)
        self.assertNotIn("youtube.com/upload", combined.lower())
        self.assertNotIn("自動公開する", combined)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_inline_javascript_parses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for page in PAGES:
                source = page.read_text(encoding="utf-8")
                match = re.search(r"<script>(.*)</script>", source, flags=re.DOTALL)
                self.assertIsNotNone(match, page)
                assert match is not None
                script = Path(temporary) / f"{page.stem}.js"
                script.write_text(match.group(1), encoding="utf-8")
                subprocess.run(
                    ["node", "--check", str(script)],
                    check=True,
                    capture_output=True,
                    text=True,
                )


class RecoverableTrashTest(unittest.TestCase):
    def environment(self, root: Path):
        projects = root / "projects"
        output = root / "output"
        return (
            patch.object(base, "ROOT", root),
            patch.object(base, "PROJECTS_DIR", projects),
            patch.object(base, "OUTPUT_DIR", output),
            patch.object(v3, "ROOT", root),
            patch.object(v3, "OUTPUT_DIR", output),
        )

    def test_generated_file_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            patches = self.environment(root)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                project = base.project_dir("demo")
                project.mkdir(parents=True)
                generated = root / "output" / "demo" / "render-assets" / "cut-001.mp4"
                generated.parent.mkdir(parents=True)
                generated.write_bytes(b"generated-cut")

                record = v3.create_trash_group(
                    project_path=project,
                    kind="generated-cut",
                    label="cut 1",
                    paths=[generated],
                )
                self.assertFalse(generated.exists())
                self.assertEqual(record["status"], "TRASHED")
                self.assertEqual(len(v3.active_trash_records(project)), 1)

                restored = v3.restore_trash_group(project, record["trashId"])
                self.assertEqual(restored["status"], "RESTORED")
                self.assertEqual(generated.read_bytes(), b"generated-cut")
                self.assertEqual(v3.load_output_state(project)["state"], "RESTORED_UNVERIFIED")

    def test_restore_never_overwrites_new_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            patches = self.environment(root)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                project = base.project_dir("demo")
                project.mkdir(parents=True)
                generated = root / "output" / "demo" / "vlog.mp4"
                generated.parent.mkdir(parents=True)
                generated.write_bytes(b"old")

                record = v3.create_trash_group(
                    project_path=project,
                    kind="generated-output-all",
                    label="all output",
                    paths=[generated],
                )
                generated.write_bytes(b"new")
                restored = v3.restore_trash_group(
                    project,
                    record["trashId"],
                    conflict_policy="rename",
                )
                self.assertEqual(generated.read_bytes(), b"new")
                restored_paths = [
                    root / item["restoredPath"] for item in restored["restoredItems"]
                ]
                self.assertEqual(len(restored_paths), 1)
                self.assertEqual(restored_paths[0].read_bytes(), b"old")
                self.assertIn("-restored-", restored_paths[0].name)

    def test_source_material_metadata_is_restored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            patches = self.environment(root)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                project = base.project_dir("demo")
                source = project / "camera" / "opening.mp4"
                source.parent.mkdir(parents=True)
                source.write_bytes(b"source")
                item = {
                    "id": "opening-1",
                    "role": "opening",
                    "type": "video",
                    "source": "camera/opening.mp4",
                    "audioMode": "source",
                }
                plan = {"version": 5, "project": "demo", "timeline": [item]}
                base.save_plan(project, plan)

                record = v3.create_trash_group(
                    project_path=project,
                    kind="source-material",
                    label="opening",
                    paths=[source],
                    metadata={"timelineIndex": 0, "timelineItem": item},
                )
                plan["timeline"].clear()
                base.save_plan(project, plan)
                v3.restore_trash_group(project, record["trashId"])

                restored_plan = base.load_plan(project)
                self.assertEqual(restored_plan["timeline"][0]["id"], "opening-1")
                self.assertTrue(source.is_file())


if __name__ == "__main__":
    unittest.main()
