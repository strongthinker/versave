#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""versave —— 给每次修改自动生成「名字_v大版本.小版本_时间戳.扩展名」的快照。

设计目标：AI（或人）改动文件后，一行命令即可产出一个可读、可排序、可回滚的版本文件，
不需要 git、不需要服务器、不改变原文件的路径（引用不会断）。

用法示例：
    python versave.py save report.md                    # -> report_v1.1_20261125_193012.md
    python versave.py save report.md --major            # -> report_v2.0_20261125_193500.md
    python versave.py list report.md                    # 查看历史
    python versave.py restore report.md -v 1.0          # 回滚（回滚前会先快照当前内容）
    python versave.py watch ./docs                      # 常驻监听，AI 一改就自动存档
"""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

__version__ = "0.1.0"

STATE_DIR = ".versave"
STATE_FILE = "state.json"
CONFIG_FILE = "config.json"

# 生成出来的快照名，例如 report_v1.2_20261125_193012.md
SNAPSHOT_RE = re.compile(r"_v(?P<major>\d+)\.(?P<minor>\d+)_(?P<ts>\d{8}_\d{6})(?:_\d+)?$")

DEFAULTS = {
    # 命名模板：{name} 原名 {major}/{minor}/{version} 版本 {timestamp} 时间 {ext} 扩展名
    "template": "{name}_v{major}.{minor}_{timestamp}{ext}",
    "time_format": "%Y%m%d_%H%M%S",
    # alongside = 与原文件同目录；也可以填相对目录，如 "versions" 或 ".versave/snapshots"
    "store": "alongside",
    "ignore_dirs": [".git", ".versave", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"],
    "ignore_globs": ["*.tmp", "*.swp", "*.lock", "~$*", ".~lock.*", "*.crdownload"],
}

COMPOUND_SUFFIXES = {".gz", ".bz2", ".xz", ".zip", ".tar", ".7z", ".zst"}


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
class VersaveError(Exception):
    """可预期的业务错误，直接打印给用户，不做 traceback。"""


def out(msg: str = "") -> None:
    try:
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()
    except UnicodeEncodeError:  # 极端终端编码
        sys.stdout.write(msg.encode("utf-8", "replace").decode("utf-8") + "\n")


def jout(payload: dict) -> None:
    out(json.dumps(payload, ensure_ascii=False, indent=2))


def now_dt() -> datetime:
    fake = os.environ.get("VERSAVE_FAKE_NOW")
    if fake:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(fake, fmt)
            except ValueError:
                pass
        raise VersaveError(f"VERSAVE_FAKE_NOW 格式无法识别: {fake}")
    return datetime.now()


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    size = float(n)
    for unit in ("KB", "MB", "GB"):
        size /= 1024.0
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
    return f"{size:.1f} GB"


def pad(text: str, width: int) -> str:
    """按显示宽度补空格（中文字符占两格）。"""
    import unicodedata

    w = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(width - w, 0)


def split_name(path: Path) -> tuple[str, str]:
    """把 report.tar.gz 拆成 ("report.tar", ".gz" 补齐为 ".tar.gz")。"""
    stem, suffix = path.stem, path.suffix
    if suffix.lower() in COMPOUND_SUFFIXES and Path(stem).suffix:
        return Path(stem).stem, Path(stem).suffix + suffix
    return stem, suffix


def find_root(start: Path) -> Path:
    """向上寻找项目根（含 .versave 或 .git 的目录），找不到就用起始目录。"""
    start = start.resolve()
    cur = start if start.is_dir() else start.parent
    for parent in [cur, *cur.parents]:
        if (parent / STATE_DIR).is_dir() or (parent / ".git").exists():
            return parent
    return cur


# --------------------------------------------------------------------------- #
# 状态与配置
# --------------------------------------------------------------------------- #
class Repo:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.dir = self.root / STATE_DIR
        self.state_path = self.dir / STATE_FILE
        self.data = self._load_state()

    def _load_state(self) -> dict:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                data.setdefault("files", {})
                data.setdefault("events", [])
                return data
            except (json.JSONDecodeError, OSError) as exc:
                raise VersaveError(f"状态文件损坏：{self.state_path}（{exc}）") from exc
        return {"files": {}, "events": []}

    def config(self) -> dict:
        cfg = dict(DEFAULTS)
        cfg_path = self.dir / CONFIG_FILE
        if cfg_path.exists():
            try:
                user_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise VersaveError(f"配置文件不是合法 JSON：{cfg_path}（{exc}）") from exc
            cfg.update({k: v for k, v in user_cfg.items() if v is not None})
        return cfg

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def rel(self, path: Path) -> str:
        path = path.resolve()
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def entry(self, rel: str) -> dict:
        files = self.data["files"]
        if rel not in files:
            files[rel] = {"version": [1, 0], "versions": [], "restores": []}
        return files[rel]

    def log(self, kind: str, rel: str, detail: dict) -> None:
        self.data["events"].append({"at": now_dt().isoformat(timespec="seconds"), "kind": kind, "file": rel, **detail})
        self.data["events"] = self.data["events"][-500:]


# --------------------------------------------------------------------------- #
# 命名
# --------------------------------------------------------------------------- #
def build_filename(cfg: dict, target: Path, major: int, minor: int, dt: datetime) -> str:
    stem, ext = split_name(target)
    values = {
        "name": stem,
        "ext": ext,
        "major": major,
        "minor": minor,
        "version": f"{major}.{minor}",
        "timestamp": dt.strftime(cfg["time_format"]),
        "date": dt.strftime("%Y%m%d"),
        "time": dt.strftime("%H%M%S"),
    }
    try:
        return cfg["template"].format(**values)
    except KeyError as exc:
        raise VersaveError(
            f"命名模板里的占位符 {exc} 不认识。可用：name / ext / major / minor / version / timestamp / date / time"
        ) from exc
    except (ValueError, IndexError) as exc:
        raise VersaveError(f"命名模板有语法错误：{cfg['template']}（{exc}）") from exc


def snapshot_dir(repo: Repo, cfg: dict, target: Path) -> Path:
    store = str(cfg.get("store", "alongside"))
    if store in ("alongside", ".", "./"):
        return target.parent
    base = Path(store)
    if not base.is_absolute():
        base = repo.root / base
    rel_parent = Path(repo.rel(target)).parent
    return base / rel_parent if rel_parent.as_posix() != "." else base


def infer_from_disk(repo: Repo, cfg: dict, target: Path) -> tuple[int, int] | None:
    """状态丢失时，从磁盘上的历史快照名里推断当前版本。"""
    folder = snapshot_dir(repo, cfg, target)
    if not folder.is_dir():
        return None
    stem, ext = split_name(target)
    best = None
    for f in folder.iterdir():
        if not f.is_file() or not f.name.startswith(stem + "_v"):
            continue
        m = SNAPSHOT_RE.search(f.stem)
        if not m:
            continue
        ver = (int(m.group("major")), int(m.group("minor")))
        if best is None or ver > best:
            best = ver
    return best


# --------------------------------------------------------------------------- #
# 核心：save
# --------------------------------------------------------------------------- #
def do_save(
    repo: Repo,
    target: Path,
    *,
    major: bool = False,
    minor: bool = False,
    set_version: str | None = None,
    note: str = "",
    force: bool = False,
    out_dir: str | None = None,
) -> dict:
    if not target.exists() or not target.is_file():
        raise VersaveError(f"文件不存在：{target}")

    cfg = repo.config()
    rel = repo.rel(target)
    entry = repo.entry(rel)
    digest = sha256_of(target)

    latest = entry["versions"][-1] if entry["versions"] else None
    if latest and latest.get("sha256") == digest and not force:
        return {"ok": True, "skipped": True, "reason": "内容与最新版本一致，未新建版本", "file": rel,
                "version": latest["version"], "snapshot": latest["path"]}

    cur_major, cur_minor = entry.get("version", [1, 0])
    first_save = not entry["versions"]
    inferred = infer_from_disk(repo, cfg, target) if first_save else None

    if set_version:
        m = re.fullmatch(r"v?(\d+)\.(\d+)", set_version.strip())
        if not m:
            raise VersaveError(f"--set 需要 a.b 形式，例如 2.3，收到：{set_version}")
        major_v, minor_v = int(m.group(1)), int(m.group(2))
    elif first_save and not inferred:
        # 首次保存：默认从 1.0 起，不浪费一个小版本号
        major_v, minor_v = (2, 0) if major else (1, 0)
    else:
        if inferred:
            cur_major, cur_minor = inferred
        major_v, minor_v = (cur_major + 1, 0) if major else (cur_major, cur_minor + 1)

    dt = now_dt()
    filename = build_filename(cfg, target, major_v, minor_v, dt)
    folder = Path(out_dir) if out_dir else snapshot_dir(repo, cfg, target)
    if not folder.is_absolute():
        folder = repo.root / folder
    folder.mkdir(parents=True, exist_ok=True)

    dest = folder / filename
    if dest.exists():  # 同一秒内重复保存
        n = 2
        while True:
            candidate = folder / f"{Path(filename).stem}_{n}{Path(filename).suffix}"
            if not candidate.exists():
                dest = candidate
                break
            n += 1
    shutil.copyfile(target, dest)

    record = {
        "version": f"{major_v}.{minor_v}",
        "major": major_v,
        "minor": minor_v,
        "path": repo.rel(dest),
        "time": dt.isoformat(timespec="seconds"),
        "sha256": digest,
        "size": target.stat().st_size,
        "note": note,
    }
    entry["versions"].append(record)
    entry["version"] = [major_v, minor_v]
    entry["working_from"] = None  # 原文件内容已是最新快照
    repo.log("save", rel, {"version": record["version"], "snapshot": record["path"]})
    repo.save()

    return {"ok": True, "skipped": False, "file": rel, "version": record["version"],
            "snapshot": record["path"], "size": record["size"], "time": record["time"]}


# --------------------------------------------------------------------------- #
# 其他命令
# --------------------------------------------------------------------------- #
def cmd_save(args) -> int:
    paths = [Path(p) for p in args.files]
    results = []
    for path in paths:
        repo = Repo(Path(args.root) if args.root else find_root(path))
        try:
            res = do_save(repo, path, major=args.major, minor=args.minor, set_version=args.set_version,
                          note=args.note or "", force=args.force, out_dir=args.out)
        except VersaveError as exc:
            results.append({"ok": False, "file": str(path), "error": str(exc)})
            if not args.json:
                sys.stderr.write(f"错误：{exc}\n")
            continue
        results.append(res)
        if not args.json:
            if res["skipped"]:
                out(f"= {res['file']}  v{res['version']}（内容未变，跳过）")
            else:
                out(f"+ {res['file']}  ->  {res['snapshot']}   v{res['version']}")

    if args.json:
        jout(results[0] if len(results) == 1 else {"ok": all(r["ok"] for r in results), "results": results})
    return 0 if all(r["ok"] for r in results) else 1


def resolve_version(repo: Repo, target: Path, want: str) -> dict:
    entry = repo.entry(repo.rel(target))
    versions = entry["versions"]
    if not versions:
        raise VersaveError(f"{target} 还没有任何历史版本")
    if want in ("latest", "", None):
        return versions[-1]
    cleaned = want.lstrip("vV")
    for rec in reversed(versions):
        if rec["version"] == cleaned:
            return rec
    raise VersaveError(f"找不到版本 {want}，现有：{', '.join(v['version'] for v in versions)}")


def cmd_list(args) -> int:
    target = Path(args.file)
    repo = Repo(Path(args.root) if args.root else find_root(target))
    entry = repo.entry(repo.rel(target))
    versions = entry["versions"]
    if args.json:
        jout({"ok": True, "file": repo.rel(target), "current": entry.get("version"),
              "versions": versions})
        return 0
    if not versions:
        out(f"{target} 还没有任何历史版本")
        return 0
    latest_v = f"{entry['version'][0]}.{entry['version'][1]}"
    hint = ""
    working_from = entry.get("working_from")
    if working_from and working_from != latest_v:
        hint = f"（工作文件当前内容 = v{working_from}，下次 save 会生成 v{entry['version'][0]}.{entry['version'][1] + 1}）"
    out(f"{repo.rel(target)}  最新快照 v{latest_v}  共 {len(versions)} 个版本 {hint}".rstrip())
    out("")
    out(pad("版本", 8) + pad("时间", 21) + "大小".rjust(9) + "   快照 / 说明")
    for rec in versions:
        note = f"  # {rec['note']}" if rec.get("note") else ""
        out(pad(f"v{rec['version']}", 8) + pad(rec["time"], 21) + human_size(rec["size"]).rjust(9)
            + f"   {rec['path']}{note}")
    return 0


def do_restore(repo: Repo, target: Path, want: str, *, snapshot_current: bool = True) -> dict:
    rec = resolve_version(repo, target, want)
    src = repo.root / rec["path"] if not Path(rec["path"]).is_absolute() else Path(rec["path"])
    if not src.exists():
        raise VersaveError(f"快照文件已丢失：{rec['path']}")

    backup = None
    if snapshot_current and target.exists():
        backup = do_save(repo, target, note=f"restore 前自动快照（即将回滚到 v{rec['version']}）")

    shutil.copyfile(src, target)
    entry = repo.entry(repo.rel(target))
    entry["restores"].append({"at": now_dt().isoformat(timespec="seconds"), "to": rec["version"]})
    entry["working_from"] = rec["version"]
    repo.log("restore", repo.rel(target), {"to": rec["version"]})
    repo.save()

    return {"ok": True, "file": repo.rel(target), "restored": rec["version"],
            "snapshot": rec["path"],
            "backup": backup["snapshot"] if backup and not backup.get("skipped") else None}


def cmd_restore(args) -> int:
    target = Path(args.file)
    repo = Repo(Path(args.root) if args.root else find_root(target))
    res = do_restore(repo, target, args.version, snapshot_current=not args.no_snapshot)
    if args.json:
        jout(res)
    else:
        out(f"↺ {res['file']} 已回滚到 v{res['restored']}")
        if res["backup"]:
            out(f"  回滚前的状态已存档：{res['backup']}")
    return 0


def do_diff(repo: Repo, target: Path, frm: str | None = None, to: str | None = None) -> dict:
    versions = repo.entry(repo.rel(target))["versions"]
    if len(versions) < 2:
        raise VersaveError("至少需要两个版本才能比较")
    new_rec = resolve_version(repo, target, to) if to else versions[-1]
    old_rec = resolve_version(repo, target, frm) if frm else versions[-2]

    def read(rec: dict) -> list[str]:
        p = repo.root / rec["path"] if not Path(rec["path"]).is_absolute() else Path(rec["path"])
        try:
            return p.read_text(encoding="utf-8").splitlines(keepends=True)
        except UnicodeDecodeError as exc:
            raise VersaveError(f"{rec['path']} 不是文本文件，无法 diff") from exc

    diff = list(difflib.unified_diff(
        read(old_rec), read(new_rec),
        fromfile=f"v{old_rec['version']} {old_rec['path']}",
        tofile=f"v{new_rec['version']} {new_rec['path']}",
    ))
    return {"ok": True, "from": old_rec["version"], "to": new_rec["version"], "diff": "".join(diff)}


def cmd_diff(args) -> int:
    target = Path(args.file)
    repo = Repo(Path(args.root) if args.root else find_root(target))
    res = do_diff(repo, target, args.frm, args.to)
    if args.json:
        jout(res)
    else:
        out(res["diff"].rstrip() or "（两个版本内容相同）")
    return 0


def cmd_prune(args) -> int:
    target = Path(args.file)
    repo = Repo(Path(args.root) if args.root else find_root(target))
    rel = repo.rel(target)
    entry = repo.entry(rel)
    versions = entry["versions"]
    if len(versions) <= args.keep:
        out(f"只有 {len(versions)} 个版本，无需清理（保留 {args.keep} 个）")
        return 0
    doomed, kept = versions[: -args.keep], versions[-args.keep:]
    if not args.yes:
        out("将删除以下旧快照（加 --yes 才会真正执行）：")
        for rec in doomed:
            out(f"  v{rec['version']}  {rec['path']}")
        return 0
    removed = 0
    for rec in doomed:
        p = repo.root / rec["path"] if not Path(rec["path"]).is_absolute() else Path(rec["path"])
        if p.exists() and p.is_file():
            p.unlink()
            removed += 1
    entry["versions"] = kept
    repo.log("prune", rel, {"removed": removed, "keep": args.keep})
    repo.save()
    out(f"已删除 {removed} 个旧快照，保留最近 {args.keep} 个")
    return 0


def iter_files(root: Path, cfg: dict):
    ignore_dirs = set(cfg["ignore_dirs"])
    globs = cfg["ignore_globs"]
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".versave")]
        for name in filenames:
            if any(fnmatch.fnmatch(name, g) for g in globs):
                continue
            if SNAPSHOT_RE.search(Path(name).stem):  # 跳过自己生成的快照，防止套娃
                continue
            yield Path(dirpath) / name


def cmd_watch(args) -> int:
    roots = [Path(p) for p in args.paths]
    for r in roots:
        if not r.exists():
            raise VersaveError(f"路径不存在：{r}")
    repo = Repo(Path(args.root) if args.root else find_root(roots[0]))
    cfg = repo.config()
    repo.dir.mkdir(parents=True, exist_ok=True)

    def scan() -> dict:
        result = {}
        for r in roots:
            base = r if r.is_dir() else r.parent
            files = iter_files(base, cfg) if r.is_dir() else iter([r])
            for f in files:
                try:
                    st = f.stat()
                except OSError:
                    continue
                result[f] = (st.st_mtime, st.st_size)
        return result

    out(f"👀 监听中：{', '.join(str(r) for r in roots)}（间隔 {args.interval}s，稳定 {args.settle}s，Ctrl+C 退出）")
    last = scan()
    pending: dict[Path, tuple[tuple, float]] = {}
    if args.initial:
        for f in last:
            try:
                res = do_save(repo, f, note="watch 启动基线")
                out(f"+ {res.get('snapshot', f)}")
            except VersaveError as exc:
                out(f"! {f}: {exc}")

    try:
        while True:
            time.sleep(args.interval)
            cur = scan()
            stamp = time.time()
            for path, sig in cur.items():
                if last.get(path) != sig:
                    pending[path] = (sig, stamp)
            for path, (sig, since) in list(pending.items()):
                if cur.get(path) == sig and stamp - since >= args.settle:
                    pending.pop(path, None)
                    try:
                        res = do_save(repo, path, note="watch 自动存档")
                    except VersaveError as exc:
                        out(f"! {path}: {exc}")
                        continue
                    if not res["skipped"]:
                        out(f"+ {res['snapshot']}   v{res['version']}   <- {repo.rel(path)}")
            for path in [p for p in pending if p not in cur]:
                pending.pop(path, None)
            last = cur
    except KeyboardInterrupt:
        out("\n已停止监听")
    return 0


def cmd_init(args) -> int:
    root = Path(args.path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    repo = Repo(root)
    repo.dir.mkdir(parents=True, exist_ok=True)
    cfg_path = repo.dir / CONFIG_FILE
    if not cfg_path.exists():
        cfg_path.write_text(json.dumps(DEFAULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    repo.save()
    out(f"已初始化：{repo.dir}（配置：{cfg_path.name}）")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="versave", description="给文件自动加「版本号+时间戳」的快照工具")
    p.add_argument("--version", action="version", version=f"versave {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--root", help="项目根目录（默认为最近的含 .versave / .git 的上级目录）")
        sp.add_argument("--json", action="store_true", help="输出 JSON，便于程序/AI 解析")

    sp = sub.add_parser("save", help="为文件创建一个新版本快照")
    sp.add_argument("files", nargs="+")
    sp.add_argument("--major", action="store_true", help="大版本 +1（1.4 -> 2.0）")
    sp.add_argument("--minor", action="store_true", help="小版本 +1（默认行为，1.4 -> 1.5）")
    sp.add_argument("--set", dest="set_version", help="直接指定版本，如 3.2")
    sp.add_argument("-m", "--note", help="给这个版本写一句说明")
    sp.add_argument("--force", action="store_true", help="内容没变也强制新建版本")
    sp.add_argument("--out", help="快照输出目录（默认跟随配置，alongside = 与原文件同目录）")
    common(sp)
    sp.set_defaults(func=cmd_save)

    sp = sub.add_parser("list", help="列出版本历史")
    sp.add_argument("file")
    common(sp)
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("restore", help="回滚到指定版本（回滚前会先给当前内容存档）")
    sp.add_argument("file")
    sp.add_argument("-v", "--version", default="latest")
    sp.add_argument("--no-snapshot", action="store_true", help="回滚前不存档当前内容（不推荐）")
    common(sp)
    sp.set_defaults(func=cmd_restore)

    sp = sub.add_parser("diff", help="比较两个版本")
    sp.add_argument("file")
    sp.add_argument("--from", dest="frm", help="起始版本，默认倒数第二个")
    sp.add_argument("--to", help="结束版本，默认最新")
    common(sp)
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("prune", help="只保留最近 N 个版本（不加 --yes 仅预览）")
    sp.add_argument("file")
    sp.add_argument("-k", "--keep", type=int, default=5)
    sp.add_argument("--yes", action="store_true")
    common(sp)
    sp.set_defaults(func=cmd_prune)

    sp = sub.add_parser("watch", help="常驻监听目录，文件一改就自动存档")
    sp.add_argument("paths", nargs="+")
    sp.add_argument("--interval", type=float, default=1.0, help="扫描间隔秒，默认 1.0")
    sp.add_argument("--settle", type=float, default=1.5, help="静默多少秒后才算写完，默认 1.5")
    sp.add_argument("--initial", action="store_true", help="启动时先给现有文件都存一个基线版本")
    common(sp)
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser("init", help="初始化一个目录（生成 .versave/ 和配置）")
    sp.add_argument("path", nargs="?", default=".")
    common(sp)
    sp.set_defaults(func=cmd_init)
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except VersaveError as exc:
        if getattr(args, "json", False):
            jout({"ok": False, "error": str(exc)})
        else:
            sys.stderr.write(f"错误：{exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
