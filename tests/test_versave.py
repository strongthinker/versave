# -*- coding: utf-8 -*-
"""versave 的行为测试：python -m unittest discover -s tests -v"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "versave.py"


class VersaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.file = self.dir / "report.md"
        self.file.write_text("line one\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, now="2026-11-25 19:30:00"):
        env = dict(os.environ, VERSAVE_FAKE_NOW=now, PYTHONIOENCODING="utf-8")
        return subprocess.run([sys.executable, str(CLI), *args], capture_output=True,
                              text=True, encoding="utf-8", env=env, cwd=self.dir)

    def snapshots(self):
        return sorted(p.name for p in self.dir.iterdir() if p.name.startswith("report_v"))

    def state(self):
        return json.loads((self.dir / ".versave" / "state.json").read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ #
    def test_first_save_creates_v1_0_and_keeps_original(self):
        res = self.run_cli("save", "report.md")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.snapshots(), ["report_v1.0_20261125_193000.md"])
        snap = self.dir / "report_v1.0_20261125_193000.md"
        self.assertEqual(snap.read_text(encoding="utf-8"), "line one\n")
        self.assertEqual(self.file.read_text(encoding="utf-8"), "line one\n")
        self.assertEqual(self.state()["files"]["report.md"]["version"], [1, 0])

    def test_unchanged_content_is_skipped(self):
        self.run_cli("save", "report.md")
        res = self.run_cli("save", "report.md", now="2026-11-25 19:31:00")
        self.assertEqual(res.returncode, 0)
        self.assertIn("跳过", res.stdout)
        self.assertEqual(len(self.snapshots()), 1)

    def test_minor_increment_and_major_bump(self):
        self.file.write_text("v1\n", encoding="utf-8")
        self.run_cli("save", "report.md")
        self.file.write_text("v2\n", encoding="utf-8")
        self.run_cli("save", "report.md", now="2026-11-25 19:31:00")
        self.file.write_text("v3\n", encoding="utf-8")
        res = self.run_cli("save", "report.md", "--major", now="2026-11-25 19:32:00")
        self.assertIn("v2.0", res.stdout)
        self.assertEqual(self.snapshots(), [
            "report_v1.0_20261125_193000.md",
            "report_v1.1_20261125_193100.md",
            "report_v2.0_20261125_193200.md",
        ])

    def test_explicit_set_version(self):
        self.file.write_text("v2\n", encoding="utf-8")
        res = self.run_cli("save", "report.md", "--set", "7.3")
        self.assertIn("report_v7.3_", res.stdout)
        self.assertEqual(self.state()["files"]["report.md"]["version"], [7, 3])

    def test_list_json(self):
        self.file.write_text("v2\n", encoding="utf-8")
        self.run_cli("save", "report.md")
        self.file.write_text("v3\n", encoding="utf-8")
        self.run_cli("save", "report.md", "-m", "加了结论", now="2026-11-25 19:31:00")
        res = self.run_cli("list", "report.md", "--json")
        payload = json.loads(res.stdout)
        self.assertEqual(len(payload["versions"]), 2)
        self.assertEqual(payload["versions"][-1]["note"], "加了结论")
        self.assertEqual(payload["current"], [1, 1])

    def test_restore_rolls_back_and_snapshots_current_first(self):
        self.run_cli("save", "report.md")
        self.file.write_text("broken edit\n", encoding="utf-8")  # 未存档的改动
        res = self.run_cli("restore", "report.md", "-v", "1.0", now="2026-11-25 19:32:00")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.file.read_text(encoding="utf-8"), "line one\n")
        names = self.snapshots()
        self.assertEqual(len(names), 2)  # 1.0 / 回滚前自动快照 1.1
        self.assertIn("report_v1.1_20261125_193200.md", names)
        self.assertEqual((self.dir / "report_v1.1_20261125_193200.md").read_text(encoding="utf-8"), "broken edit\n")

    def test_restore_unknown_version_fails(self):
        self.run_cli("save", "report.md")
        res = self.run_cli("restore", "report.md", "-v", "9.9")
        self.assertEqual(res.returncode, 1)
        self.assertIn("找不到版本", res.stderr)

    def test_diff(self):
        self.file.write_text("a\nb\n", encoding="utf-8")
        self.run_cli("save", "report.md")
        self.file.write_text("a\nB\n", encoding="utf-8")
        self.run_cli("save", "report.md", now="2026-11-25 19:31:00")
        res = self.run_cli("diff", "report.md")
        self.assertIn("-b", res.stdout)
        self.assertIn("+B", res.stdout)

    def test_compound_extension_stays_intact(self):
        archive = self.dir / "data.tar.gz"
        archive.write_bytes(b"bytes")
        res = self.run_cli("save", "data.tar.gz")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue((self.dir / "data.tar_v1.0_20261125_193000.tar.gz").exists()
                        or (self.dir / "data_v1.0_20261125_193000.tar.gz").exists())

    def test_archive_store_config(self):
        self.run_cli("init", ".")
        cfg_path = self.dir / ".versave" / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["store"] = ".versave/snapshots"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        self.run_cli("save", "report.md")
        target = self.dir / ".versave" / "snapshots" / "report_v1.0_20261125_193000.md"
        self.assertTrue(target.exists(), list(self.dir.rglob("*")))
        self.assertEqual(self.snapshots(), [])

    def test_prune_requires_yes(self):
        for i in range(3):
            self.file.write_text(f"rev {i}\n", encoding="utf-8")
            self.run_cli("save", "report.md", now=f"2026-11-25 19:3{i}:00")
        preview = self.run_cli("prune", "report.md", "-k", "1")
        self.assertIn("--yes", preview.stdout)
        self.assertEqual(len(self.snapshots()), 3)
        done = self.run_cli("prune", "report.md", "-k", "1", "--yes")
        self.assertEqual(done.returncode, 0)
        self.assertEqual(self.snapshots(), ["report_v1.2_20261125_193200.md"])

    def test_missing_file_reports_error(self):
        res = self.run_cli("save", "nope.md")
        self.assertEqual(res.returncode, 1)
        self.assertIn("文件不存在", res.stderr)

    def test_json_error_channel(self):
        res = self.run_cli("save", "nope.md", "--json")
        payload = json.loads(res.stdout)
        self.assertFalse(payload["ok"])

    def test_watch_autosaves_on_change(self):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.Popen(
            [sys.executable, str(CLI), "watch", ".", "--interval", "0.2", "--settle", "0.3", "--initial"],
            cwd=self.dir, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            import time as _t

            _t.sleep(1.2)
            self.file.write_text("line one\nline two\n", encoding="utf-8")
            _t.sleep(2.5)
        finally:
            proc.terminate()
            proc.wait(timeout=5)

        payload = json.loads((self.dir / ".versave" / "state.json").read_text(encoding="utf-8"))
        versions = payload["files"]["report.md"]["versions"]
        self.assertGreaterEqual(len(versions), 2, versions)  # 基线 + 改动
        self.assertTrue(any("line two" in (self.dir / v["path"]).read_text(encoding="utf-8") for v in versions))


if __name__ == "__main__":
    unittest.main(verbosity=2)
