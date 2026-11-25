#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 versave 安装到各家 AI 工具能读到的地方。

    python install.py --list             # 看支持哪些工具、装到哪
    python install.py                    # 自动探测已安装的 AI 工具并装进去
    python install.py --tool all -p .    # skill + 项目内所有规则文件
    python install.py --tool cursor -p . # 只给 Cursor 写规则
    python install.py --print-mcp        # 打印 MCP 配置（粘到客户端里）

设计原则：可重复运行、不覆盖原有内容（用标记块）、改动前自动备份。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BEGIN = "<!-- versave:begin（由 install.py 生成，可重复运行） -->"
END = "<!-- versave:end -->"

SKIP_DIRS = {".git", ".versave", "demo", "tests", "__pycache__", ".github", ".venv", ".idea", ".vscode"}
SKIP_FILES = {".gitignore", "install.py"}

# kind=skill 的会整包复制到技能目录；kind=rules 的往项目里注入一个标记块
TOOLS = {
    "workbuddy": {"label": "WorkBuddy", "kind": "skill", "path": "~/.workbuddy/skills/versave"},
    "claude": {"label": "Claude Code / Claude 桌面端技能", "kind": "skill", "path": "~/.claude/skills/versave"},
    "claudecode": {"label": "Claude Code（CLAUDE.md 规则）", "kind": "rules",
                   "file": "CLAUDE.md", "src": "integrations/CLAUDE.md"},
    "codex": {"label": "Codex / 通用 AGENTS.md", "kind": "rules",
              "file": "AGENTS.md", "src": "integrations/AGENTS.md"},
    "cursor": {"label": "Cursor 项目规则", "kind": "rules",
               "file": ".cursor/rules/versave.mdc", "src": "integrations/cursor-versave.mdc"},
    "windsurf": {"label": "Windsurf 项目规则", "kind": "rules",
                 "file": ".windsurf/rules/versave.md", "src": "integrations/windsurf-rules.md"},
    "copilot": {"label": "GitHub Copilot 指令", "kind": "rules",
                "file": ".github/copilot-instructions.md", "src": "integrations/copilot-instructions.md"},
    "gemini": {"label": "Gemini CLI", "kind": "rules", "file": "GEMINI.md", "src": "integrations/GEMINI.md"},
    "cline": {"label": "Cline / Roo Code", "kind": "rules", "file": ".clinerules", "src": "integrations/clinerules"},
    "chat": {"label": "纯聊天 AI（手动粘贴）", "kind": "prompt", "file": "versave-prompt.md",
             "src": "prompts/chat-prompt.md"},
}
RULE_TOOLS = [k for k, v in TOOLS.items() if v["kind"] in ("rules", "prompt")]


def home_dir() -> Path:
    return Path(os.environ.get("VERSAVE_HOME") or Path.home()).expanduser()


def log(msg: str, dry: bool = False) -> None:
    print(("[dry] " if dry else "") + msg)


def skill_files() -> list[Path]:
    files = []
    for path in HERE.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(HERE).parts):
            continue
        if path.is_file() and path.name not in SKIP_FILES:
            files.append(path)
    return sorted(files)


def install_skill(tool: str, dry: bool) -> None:
    raw = TOOLS[tool]["path"]
    target = home_dir() / raw[2:] if raw.startswith("~/") else Path(raw).expanduser()
    if dry:
        log(f"{tool}: 复制 {len(skill_files())} 个文件 -> {target}", dry=True)
        return
    target.mkdir(parents=True, exist_ok=True)
    for src in skill_files():
        dest = target / src.relative_to(HERE)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    log(f"✓ {TOOLS[tool]['label']}  →  {target}")


def split_frontmatter(text: str) -> tuple[str, str]:
    """把 .mdc 之类的 YAML 头拆出来，返回 (frontmatter, 正文)。"""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return "---" + parts[1] + "---", parts[2].lstrip("\n")
    return "", text


def inject(target: Path, block: str, dry: bool) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        if dry:
            return "create"
        target.write_text(block + "\n", encoding="utf-8")
        return "create"

    old = target.read_text(encoding="utf-8")
    if BEGIN in old and END in old:
        start, end = old.index(BEGIN), old.index(END) + len(END)
        new = old[:start] + block + old[end:]
        if new == old:
            return "unchanged"
        if not dry:
            target.write_text(new, encoding="utf-8")
        return "update"

    if not dry:
        shutil.copy2(target, target.with_suffix(target.suffix + ".versave-bak"))
        sep = "" if old.endswith("\n") else "\n"
        target.write_text(old + sep + "\n" + block + "\n", encoding="utf-8")
    return "append"


def install_rules(tool: str, project: Path, dry: bool) -> None:
    meta = TOOLS[tool]
    src = HERE / meta["src"]
    if not src.exists():
        raise SystemExit(f"缺少模板文件：{src}")
    target = project / meta["file"]
    body = src.read_text(encoding="utf-8")

    if meta["kind"] == "prompt":  # 纯聊天提示词：原样给一份，不加标记块，方便直接复制
        if target.exists():
            log(f"○ {meta['label']} 已存在，跳过  {target}")
            return
        if not dry:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        log(f"✓ {meta['label']}  已生成  {target}（复制全文贴给 AI 即可）")
        return

    is_new = not target.exists()
    frontmatter, body_text = split_frontmatter(body)
    block = f"{BEGIN}\n{body_text.strip()}\n{END}"
    if is_new and frontmatter:  # Cursor 等要求 frontmatter 必须在最顶部
        block = f"{frontmatter}\n\n{block}"
    action = inject(target, block, dry)
    label = {"create": "创建", "update": "更新", "append": "追加（原文件已备份）", "unchanged": "已是最新"}[action]
    log(f"{'○' if action == 'unchanged' else '✓'} {meta['label']}  {label}  {target}")


def mcp_config() -> dict:
    server = {"command": sys.executable, "args": [str(HERE / "mcp_server.py")]}
    return {"mcpServers": {"versave": {**server, "env": {}}}}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="把 versave 安装到各家 AI 工具")
    p.add_argument("-t", "--tool", default="auto",
                   help=f"要装给谁：auto / all / skill / {', '.join(TOOLS)}")
    p.add_argument("-p", "--project", default=".", help="项目目录（写规则文件用），默认当前目录")
    p.add_argument("--home", help="覆盖用户主目录（测试用）")
    p.add_argument("--dry-run", action="store_true", help="只打印将要做什么")
    p.add_argument("--list", action="store_true", help="列出支持的工具与安装位置")
    p.add_argument("--print-mcp", action="store_true", help="输出 MCP 客户端配置")
    args = p.parse_args(argv)

    if args.home:
        os.environ["VERSAVE_HOME"] = args.home

    if args.list:
        print("支持的工具：\n")
        for key, meta in TOOLS.items():
            where = meta.get("path") or f"{meta['file']}（项目内）"
            print(f"  {key:<10} {meta['label']:<28} {where}")
        print("\n用法：python install.py --tool all -p .")
        return 0

    if args.print_mcp:
        print(json.dumps(mcp_config(), ensure_ascii=False, indent=2))
        print("\n# 粘到客户端配置里即可：")
        print("#   Claude 桌面端  claude_desktop_config.json")
        print("#   Cursor         .cursor/mcp.json")
        print("#   Cline          cline_mcp_settings.json")
        print("#   WorkBuddy      ~/.workbuddy/mcp.json")
        return 0

    project = Path(args.project).resolve()
    choice = args.tool

    if choice == "auto":
        targets = []
        if (home_dir() / ".workbuddy").exists():
            targets.append("workbuddy")
        if (home_dir() / ".claude").exists():
            targets.append("claude")
        if not targets:
            print("没有探测到已安装的 AI 工具。可以手动指定：")
            print("  python install.py --tool workbuddy     # 装技能")
            print("  python install.py --tool cursor -p .   # 写项目规则")
            print("  python install.py --tool chat          # 导出提示词，手动粘贴")
            return 0
        for t in targets:
            install_skill(t, args.dry_run)
        print("\n提示：跑 `python install.py --tool all -p .` 可以顺带写好项目规则文件。")
        return 0

    if choice == "skill":
        for t in ("workbuddy", "claude"):
            install_skill(t, args.dry_run)
        return 0

    if choice == "all":
        for t in ("workbuddy", "claude"):
            install_skill(t, args.dry_run)
        for t in RULE_TOOLS:
            install_rules(t, project, args.dry_run)
        print(f"\nMCP 配置（可选）：python install.py --print-mcp")
        return 0

    if choice not in TOOLS:
        raise SystemExit(f"未知工具：{choice}（可选：auto / all / skill / {', '.join(TOOLS)}）")

    if TOOLS[choice]["kind"] == "skill":
        install_skill(choice, args.dry_run)
    else:
        install_rules(choice, project, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
