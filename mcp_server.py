#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""versave MCP 服务：把版本快照能力暴露成 MCP 工具，任何支持 MCP 的 AI 客户端都能直接调用。

传输：stdio，换行分隔的 JSON-RPC 2.0（MCP 标准）。
配置示例见同目录 mcp.json。

手动自测：
    echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python mcp_server.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import versave  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "versave", "version": versave.__version__}

TOOLS = [
    {
        "name": "versave_save",
        "description": "为文件创建一个带「版本号 + 时间戳」的快照，返回快照路径和新版本号。"
                       "普通修改用默认（小版本 +1）；结构性重写或定稿用 mode=major；用户指定版本用 mode=set。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "要存档的文件路径（绝对或相对当前目录）"},
                "note": {"type": "string", "description": "这次改动的说明，会记进版本历史"},
                "mode": {"type": "string", "enum": ["minor", "major", "set"], "default": "minor",
                         "description": "minor=小版本+1（默认）；major=大版本+1；set=用 version 指定"},
                "version": {"type": "string", "description": "mode=set 时的版本号，如 3.2"},
                "force": {"type": "boolean", "description": "内容没变也强制存档，默认 false"},
            },
            "required": ["file"],
        },
    },
    {
        "name": "versave_list",
        "description": "列出某个文件的所有历史版本：版本号、时间、大小、快照路径、备注。",
        "inputSchema": {
            "type": "object",
            "properties": {"file": {"type": "string", "description": "文件路径"}},
            "required": ["file"],
        },
    },
    {
        "name": "versave_restore",
        "description": "把文件回滚到指定版本。回滚前会自动把当前内容存成一版，误回滚可以再救回来。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "文件路径"},
                "version": {"type": "string", "description": "目标版本，如 1.2；默认 latest"},
                "snapshot_current": {"type": "boolean", "default": True,
                                     "description": "回滚前是否先给当前内容存档，默认 true"},
            },
            "required": ["file"],
        },
    },
    {
        "name": "versave_diff",
        "description": "对比同一文件的两个版本，返回 unified diff。默认对比最近两版。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "from_version": {"type": "string", "description": "起始版本，默认倒数第二个"},
                "to_version": {"type": "string", "description": "结束版本，默认最新"},
            },
            "required": ["file"],
        },
    },
]


def _repo(path: str) -> tuple[versave.Repo, Path]:
    target = Path(path).expanduser()
    return versave.Repo(versave.find_root(target)), target


def tool_save(args: dict) -> dict:
    repo, target = _repo(args["file"])
    mode = args.get("mode", "minor")
    if mode == "set" and not args.get("version"):
        raise versave.VersaveError("mode=set 时必须提供 version，例如 3.2")
    return versave.do_save(
        repo, target,
        major=(mode == "major"),
        set_version=args.get("version") if mode == "set" else None,
        note=args.get("note", ""),
        force=bool(args.get("force", False)),
    )


def tool_list(args: dict) -> dict:
    repo, target = _repo(args["file"])
    entry = repo.entry(repo.rel(target))
    return {"ok": True, "file": repo.rel(target), "latest": entry.get("version"),
            "count": len(entry["versions"]), "versions": entry["versions"]}


def tool_restore(args: dict) -> dict:
    repo, target = _repo(args["file"])
    return versave.do_restore(repo, target, args.get("version") or "latest",
                              snapshot_current=bool(args.get("snapshot_current", True)))


def tool_diff(args: dict) -> dict:
    repo, target = _repo(args["file"])
    return versave.do_diff(repo, target, args.get("from_version"), args.get("to_version"))


HANDLERS = {
    "versave_save": tool_save,
    "versave_list": tool_list,
    "versave_restore": tool_restore,
    "versave_diff": tool_diff,
}


def _result(req_id, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": payload}


def _error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(req: dict) -> dict | None:
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        wanted = params.get("protocolVersion")
        return _result(req_id, {
            "protocolVersion": wanted if wanted in ("2024-11-05", "2025-03-26", "2025-06-18") else PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if not handler:
            return _error(req_id, -32602, f"未知工具：{name}")
        try:
            payload = handler(args)
        except versave.VersaveError as exc:
            return _result(req_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        except Exception as exc:  # 不让客户端因为意外异常直接断连
            return _result(req_id, {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                                    "isError": True})
        return _result(req_id, {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)},
                                            ]})
    if req_id is not None:
        return _error(req_id, -32601, f"不支持的方法：{method}")
    return None


def main() -> int:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except json.JSONDecodeError as exc:
            sys.stdout.write(json.dumps(_error(None, -32700, f"JSON 解析失败：{exc}")) + "\n")
            sys.stdout.flush()
            continue
        try:
            resp = handle(req if isinstance(req, dict) else {})
        except Exception as exc:  # 兜底，保证 stdout 始终是合法 JSON-RPC
            resp = _error(req.get("id") if isinstance(req, dict) else None, -32603,
                          f"{type(exc).__name__}: {exc}")
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
