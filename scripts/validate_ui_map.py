#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ID_RE = re.compile(r'\bid=["\']([^"\']+)["\']')
SHOW_RE = re.compile(r"show\(['\"]([^'\"]+)['\"]\)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, default=Path("web_console/static/index.html"))
    parser.add_argument("--manifest", type=Path, default=Path("debug/ui-map.json"))
    parser.add_argument("--report", type=Path, default=Path("debug/ui-validation-report.json"))
    args = parser.parse_args()

    html = args.html.read_text(encoding="utf-8")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    ids = set(ID_RE.findall(html))
    show_targets = set(SHOW_RE.findall(html))

    missing_screens = [s["id"] for s in manifest["screens"] if s["id"] not in ids and s["id"] not in {"managePage", "downloadTarget"}]
    missing_actions = []
    for action in manifest["actions"]:
        action_id = action["id"].split("-", 1)[0]
        if action_id not in ids:
            missing_actions.append(action["id"])

    panel_ids = {s["id"] for s in manifest["screens"] if s["id"].endswith("Panel")}
    unreachable_declared_panels = sorted(panel_ids - show_targets - {"projectPanel"})
    unknown_show_targets = sorted(show_targets - panel_ids)

    report = {
        "source": str(args.html),
        "manifest": str(args.manifest),
        "declared_screen_count": len(manifest["screens"]),
        "declared_action_count": len(manifest["actions"]),
        "html_id_count": len(ids),
        "show_targets": sorted(show_targets),
        "missing_screens": missing_screens,
        "missing_actions": missing_actions,
        "unreachable_declared_panels": unreachable_declared_panels,
        "unknown_show_targets": unknown_show_targets,
        "decision": "PASS" if not (missing_screens or missing_actions or unreachable_declared_panels or unknown_show_targets) else "FAIL",
        "note": "This is UI_BOOTSTRAP static validation. observed_target and screenshots remain unverified until browser automation runs."
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
