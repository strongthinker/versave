# -*- coding: utf-8 -*-
"""安装器测试：目标目录结构、幂等性、对已有文件的保护。"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install.py"
MARK = "versave:begin"


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.home.mkdir()
        self.project = base / "proj"
        self.project.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_install(self, *args):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        return subprocess.run([sys.executable, str(INSTALL), *args, "--home", str(self.home)],
                              capture_output=True, text=True, encoding="utf-8", env=env,
                              cwd=self.project, timeout=120)

    def test_list_shows_tools(self):
        res = self.run_install("--list")
        self.assertEqual(res.returncode, 0, res.stderr)
        for key in ("workbuddy", "claude", "cursor", "copilot", "chat"):
            self.assertIn(key, res.stdout)

    def test_all_installs_skill_and_rules(self):
        res = self.run_install("--tool", "all", "-p", str(self.project))
        self.assertEqual(res.returncode, 0, res.stderr)

        skill = self.home / ".workbuddy" / "skills" / "versave"
        self.assertTrue((skill / "SKILL.md").exists())
        self.assertTrue((skill / "versave.py").exists())
        self.assertTrue((skill / "mcp_server.py").exists())
        self.assertTrue((self.home / ".claude" / "skills" / "versave" / "SKILL.md").exists())

        for rel in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "version", ".clinerules",
                    ".github/copilot-instructions.md", ".cursor/rules/versave.mdc",
                    ".windsurf/rules/versave.md", "versave-prompt.md"):
            if rel == "version":
                continue
            self.assertTrue((self.project / rel).exists(), rel)

        agents = (self.project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("versave save", agents)

    def test_rules_are_idempotent(self):
        self.run_install("--tool", "all", "-p", str(self.project))
        first = (self.project / "AGENTS.md").read_text(encoding="utf-8")
        self.run_install("--tool", "all", "-p", str(self.project))
        second = (self.project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(first, second)
        self.assertEqual(second.count(MARK), 1)

    def test_existing_rules_file_is_backed_up(self):
        target = self.project / "AGENTS.md"
        target.write_text("# 我自己的规则\n\n别动这一行。\n", encoding="utf-8")
        res = self.run_install("--tool", "codex", "-p", str(self.project))
        self.assertEqual(res.returncode, 0, res.stderr)
        text = target.read_text(encoding="utf-8")
        self.assertIn("别动这一行", text)
        self.assertIn(MARK, text)
        self.assertTrue((self.project / "AGENTS.md.versave-bak").exists())

    def test_cursor_rule_keeps_frontmatter(self):
        self.run_install("--tool", "cursor", "-p", str(self.project))
        text = (self.project / ".cursor" / "rules" / "versave.mdc").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---"))
        self.assertIn("alwaysApply", text)
        self.assertIn("versave save", text)

    def test_prompt_for_chat_ai(self):
        self.run_install("--tool", "chat", "-p", str(self.project))
        text = (self.project / "versave-prompt.md").read_text(encoding="utf-8")
        self.assertIn("_v1.0_", text)
        self.assertIn("大版本", text)

    def test_dry_run_writes_nothing(self):
        res = self.run_install("--tool", "all", "-p", str(self.project), "--dry-run")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("dry", res.stdout)
        self.assertFalse((self.home / ".workbuddy").exists())
        self.assertFalse((self.project / "AGENTS.md").exists())

    def test_print_mcp(self):
        res = self.run_install("--print-mcp")
        cfg = json.loads(res.stdout.split("\n#")[0])
        args = cfg["mcpServers"]["versave"]["args"]
        self.assertTrue(args[0].endswith("mcp_server.py"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
