# -*- coding: utf-8 -*-
"""MCP 服务测试：走真实 stdio JSON-RPC，验证客户端能看到的工具与返回。"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server.py"


class McpServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.file = self.dir / "report.md"
        self.file.write_text("第一版\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def rpc(self, *messages):
        payload = "\n".join(json.dumps(m, ensure_ascii=False) for m in messages) + "\n"
        env = dict(os.environ, PYTHONIOENCODING="utf-8", VERSAVE_FAKE_NOW="2026-11-25 19:30:00")
        res = subprocess.run([sys.executable, str(SERVER)], input=payload, capture_output=True,
                             text=True, encoding="utf-8", env=env, cwd=self.dir, timeout=60)
        return [json.loads(line) for line in res.stdout.splitlines() if line.strip()]

    def test_initialize_and_tools_list(self):
        init, listing = self.rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        self.assertEqual(init["result"]["serverInfo"]["name"], "versave")
        self.assertIn("tools", init["result"]["capabilities"])
        names = {t["name"] for t in listing["result"]["tools"]}
        self.assertEqual(names, {"versave_save", "versave_list", "versave_restore", "versave_diff"})

    def test_save_then_list_via_mcp(self):
        save, listing = self.rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "versave_save",
                        "arguments": {"file": "report.md", "note": "初稿"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "versave_list", "arguments": {"file": "report.md"}}},
        )
        saved = json.loads(save["result"]["content"][0]["text"])
        self.assertEqual(saved["version"], "1.0")
        self.assertTrue((self.dir / saved["snapshot"]).exists())

        listed = json.loads(listing["result"]["content"][0]["text"])
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["versions"][0]["note"], "初稿")

    def test_major_mode_and_restore(self):
        self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": "versave_save", "arguments": {"file": "report.md"}}})
        self.file.write_text("第二版\n", encoding="utf-8")
        major, restore = self.rpc(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "versave_save", "arguments": {"file": "report.md", "mode": "major"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "versave_restore", "arguments": {"file": "report.md", "version": "1.0"}}},
        )
        self.assertEqual(json.loads(major["result"]["content"][0]["text"])["version"], "2.0")
        restored = json.loads(restore["result"]["content"][0]["text"])
        self.assertEqual(restored["restored"], "1.0")
        self.assertEqual(self.file.read_text(encoding="utf-8"), "第一版\n")

    def test_tool_error_is_reported_not_crashed(self):
        res, = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": "versave_save", "arguments": {"file": "missing.md"}}})
        self.assertTrue(res["result"]["isError"])
        self.assertIn("文件不存在", res["result"]["content"][0]["text"])

    def test_unknown_tool(self):
        res, = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": "nope", "arguments": {}}})
        self.assertEqual(res["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main(verbosity=2)
