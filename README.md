# versave

> 给每次改动自动生成 **`名字_v大版本.小版本_时间戳.扩展名`** 的快照。
> 一个文件，零依赖，为「AI 改文件」这个场景设计。

```text
report.md
report_v1.0_20261125_193012.md     ← 第 1 次
report_v1.1_20261125_194501.md     ← AI 改了第 2 次
report_v1.2_20261125_200233.md     ← 第 3 次
report_v2.0_20261126_091500.md     ← 定稿，大版本 +1
```

原文件始终叫 `report.md`（路径不变，链接和引用不会断），历史全部带版本号和时间戳，
按文件名排序就是时间顺序，双击就能打开，不需要任何客户端。

---

## 为什么自己写一个

GitHub 上相关的东西不少，但没有一个正好做这件事：

| 项目 | 它做什么 | 缺什么 |
| --- | --- | --- |
| [jaywgraves/version](https://github.com/jaywgraves/version) | 复制文件并插入日期时间戳 `sample.20201002.084532.output` | 没有版本号，不会 a.b 递增 |
| [VCP / vertical-copy](https://github.com/grzbla/vertical-copy) | 覆盖前把旧版本存进隐藏的 `.v/` 目录 | 版本藏在目录里、名字是纯时间戳、要手动翻 |
| [ts-creator](https://github.com/codesalittle/ts-creator) | 整个项目打包成 `proj_v2.3.1.zip` | 管整个项目，不管单文件；版本号靠手输 |
| Git tag / Release | 仓库级语义化版本 | 管的是仓库，不是「某个 md 改了三次」 |
| VS Code Local History / Obsidian 文件恢复 | 编辑器内置的隐式历史 | 文件名不可控、不可导出、不可交给 AI 调用 |

缺的那一块很清楚：**单文件级别的 a.b 版本号自动递增 + 时间戳命名 + 可被程序/AI 调用**。
所以有了 versave。

---

## 安装

只需要 Python 3.9+，没有第三方依赖。

```bash
# 方式零：从 GitHub 克隆后一键装给所有 AI（推荐）
git clone https://github.com/strongthinker/versave.git
cd versave
python install.py --tool all -p <你的项目目录>

# 方式一：直接跑
python versave.py save report.md

# 方式二：装成命令（推荐）
pip install -e .
versave save report.md

# 方式三：Windows 下加个 bat
# 把 versave.cmd 放到 PATH 里，然后 versave save report.md
```

---

## 装给所有 AI（重点）

这个仓库同时是一个**通用 skill**：同一套规则，四种接入方式，覆盖市面上主流 AI 工具。

```bash
python install.py --list            # 看支持哪些工具
python install.py                   # 自动探测已装的 AI 并装进去
python install.py --tool all -p .   # 技能 + 项目内所有规则文件
python install.py --dry-run         # 只看会做什么，不写盘
```

| 你的 AI 工具 | 用哪种形态 | 安装后落在哪 | 命令 |
| --- | --- | --- | --- |
| WorkBuddy | 技能（`SKILL.md`） | `~/.workbuddy/skills/versave/` | `--tool workbuddy` |
| Claude Code / Claude 桌面端 | 技能（`SKILL.md`） | `~/.claude/skills/versave/` | `--tool claude` |
| Codex / Jules / Amp / 通用 agent | `AGENTS.md` 规则 | 项目根 `AGENTS.md` | `--tool codex -p .` |
| Claude Code（不想用技能时） | `CLAUDE.md` | 项目根 `CLAUDE.md` | `--tool claudecode -p .` |
| Cursor | Project Rule（`.mdc`） | `.cursor/rules/versave.mdc` | `--tool cursor -p .` |
| Windsurf | Rules（`always_on`） | `.windsurf/rules/versave.md` | `--tool windsurf -p .` |
| GitHub Copilot | 指令文件 | `.github/copilot-instructions.md` | `--tool copilot -p .` |
| Gemini CLI | `GEMINI.md` | 项目根 `GEMINI.md` | `--tool gemini -p .` |
| Cline / Roo Code | `.clinerules` | 项目根 `.clinerules` | `--tool cline -p .` |
| 网页版 ChatGPT / DeepSeek / Kimi | 纯提示词 | `versave-prompt.md` | `--tool chat -p .` |
| 任意支持 MCP 的客户端 | MCP 服务 | 见下方配置 | `--print-mcp` |

所有规则文件都是**标记块注入**：重复运行只更新 `<!-- versave:begin/end -->` 之间的内容，
你原有的规则一个字不动；首次追加时会先备份成 `*.versave-bak`。

### 纯聊天 AI（没有文件系统）

`--tool chat` 生成的 `versave-prompt.md` 直接复制粘贴进对话即可。它走**降级规则**：
仍然按 `名字_v1.0_YYYYMMDD_HHMMSS.ext` 命名、每次小版本 +1、附一张版本表，
只是没有 `restore` / `diff` 这些命令可用。

### MCP（给能调工具的客户端）

```bash
python install.py --print-mcp
```

把输出的 JSON 粘到对应配置里即可：Claude 桌面端 `claude_desktop_config.json`、
Cursor `.cursor/mcp.json`、Cline `cline_mcp_settings.json`、WorkBuddy `~/.workbuddy/mcp.json`。

暴露四个工具：`versave_save` / `versave_list` / `versave_restore` / `versave_diff`。
好处是不依赖模型“记得规则”，由客户端直接把工具塞给模型，成功率最高。

---

## 命令

| 命令 | 作用 |
| --- | --- |
| `versave save <file>...` | 新建一个版本快照（默认小版本 +1） |
| `versave save <file> --major` | 大版本 +1，小版本归零（1.4 → 2.0） |
| `versave save <file> --set 3.2` | 直接指定版本号 |
| `versave save <file> -m "补充了第三节"` | 给版本写说明，`list` 里能看到 |
| `versave list <file>` | 看历史（表格 / `--json`） |
| `versave restore <file> -v 1.0` | 回滚，**回滚前自动把当前内容存一版**，所以回滚本身也能撤销 |
| `versave diff <file>` | 对比最近两版；`--from 1.0 --to 1.2` 指定范围 |
| `versave prune <file> -k 5` | 只留最近 5 版；不加 `--yes` 只预览不删 |
| `versave watch ./docs` | 常驻监听，文件一改就自动存档（AI 场景最省事） |
| `versave init .` | 生成 `.versave/config.json`，可改命名模板 |

所有命令都支持 `--json`，输出结构化结果，方便 AI 或脚本读取快照路径：

```bash
$ versave save report.md --json
{
  "ok": true,
  "skipped": false,
  "file": "report.md",
  "version": "1.1",
  "snapshot": "report_v1.1_20261125_194501.md",
  "size": 2048,
  "time": "2026-11-25T19:45:01"
}
```

---

## 命名规则

默认模板：

```text
{name}_v{major}.{minor}_{timestamp}{ext}
```

可在 `.versave/config.json` 里改，占位符：
`{name}` `{ext}` `{major}` `{minor}` `{version}` `{timestamp}` `{date}` `{time}`。

```json
{
  "template": "{name}_v{major}.{minor}_{timestamp}{ext}",
  "time_format": "%Y%m%d_%H%M%S",
  "store": "alongside"
}
```

`store` 两种玩法：

- `"alongside"`（默认）：快照和原文件放同一目录，肉眼可见、随手能打开，符合「文件名就是版本」的直觉。
- `".versave/snapshots"`：快照收进隐藏目录，原目录保持干净（适合代码仓库）。

细节处理：

- `report.tar.gz` → `report_v1.0_20261125_193012.tar.gz`，扩展名不会被拆坏。
- 同一秒内连存两次 → 自动加 `_2` 后缀，绝不覆盖已有文件。
- 内容没变 → 默认跳过、不浪费版本号（`--force` 可强制）。
- 状态文件丢了 → 从磁盘上的快照名反推当前版本，不会退回 1.0 撞名。

---

## 接到 AI 工作流里

### 方式 A：让 AI 自己调（最可控）

不用自己写规则，`python install.py --tool all -p .` 会按工具类型生成对应文件
（`SKILL.md` / `AGENTS.md` / `CLAUDE.md` / `.cursor/rules/versave.mdc` …），内容等价于：

```markdown
## 文件修改规则
每次修改任何交付文件（.md/.docx/.py/...）后，必须执行：
  python versave.py save <被修改的文件> -m "<一句话说明这次改了什么>" --json
不要手工给文件加版本后缀，版本号由 versave 统一管理。
若返回 skipped=true，说明内容没变，不用重试。
```

AI 拿到 JSON 里的 `snapshot` 字段，就能在回复里告诉你「本次产出：report_v1.1_...md」。
想更硬一点，用 MCP（`--print-mcp`）：工具由客户端注入，不依赖模型记不记得规则。

### 方式 B：watch 常驻（零侵入）

```bash
versave watch . --initial
```

不管 AI 用什么工具写文件，落盘稳定 1.5 秒后自动存一版，终端里直接打出快照名。
适合「AI 在 IDE 里改了十几个文件，我不想每个都手动 save」。

### 方式 C：git hook

```bash
# .git/hooks/pre-commit
for f in $(git diff --cached --name-only --diff-filter=ACM); do
  case "$f" in *.md|*.txt) python versave.py save "$f" -m "commit 前快照" ;; esac
done
```

---

## 仓库结构

```text
versave/
├── SKILL.md                  # 通用 skill 定义（Claude / WorkBuddy 等直接读）
├── versave.py                # 命令行实现，纯标准库
├── mcp_server.py             # MCP 服务：save / list / restore / diff 四个工具
├── mcp.json                  # MCP 配置模板
├── install.py                # 一键装给各家 AI（可重复运行、有备份）
├── integrations/             # 各工具规则模板
│   ├── AGENTS.md             # Codex / 通用 agent
│   ├── CLAUDE.md             # Claude Code
│   ├── GEMINI.md             # Gemini CLI
│   ├── copilot-instructions.md
│   ├── cursor-versave.mdc    # Cursor Project Rule
│   ├── windsurf-rules.md
│   └── clinerules            # Cline / Roo Code
├── prompts/chat-prompt.md    # 纯聊天 AI 的降级提示词
├── tests/                    # 27 项测试（CLI / MCP / 安装器）
└── demo/                     # 演示产物
```

## 项目内目录结构

```text
project/
├── report.md                      # 工作文件，名字永远不变
├── report_v1.0_20261125_193012.md # 快照
├── report_v1.1_20261125_194501.md
└── .versave/
    ├── state.json                 # 每个文件的当前版本、历史、哈希、备注
    └── config.json                # 可选，命名模板等
```

`state.json` 是唯一索引，但**不是唯一真相**：所有版本信息都能从快照文件名重建，
状态文件删了也不会丢历史。

---

## 设计取舍

- **不覆盖原文件**：AI 的下游流程（导出、构建、引用）都盯着 `report.md`，改名会连锁炸掉。
  「带版本的是快照，不带版本的是工作副本」是这套工具的核心约定。
- **用哈希判断是否真改了**：AI 经常「重写一遍但其实一字未改」，靠 mtime 会产生大量废版本。
- **回滚先存档**：误回滚本身也能撤销，避免「为了救 A 结果把 B 弄丢」。
- **默认不删任何东西**：`prune` 必须显式 `--yes`，且只删自己生成在版本目录里的快照。
- **纯 stdlib**：任何有 Python 的机器（包括 CI 容器、AI 沙箱）都能跑，不需要装包。

## 已知边界

- 不做内容去重/压缩，每版都是完整副本（文本文件无所谓，大二进制请配 `store` 归档 + `prune`）。
- 不做并发写锁：同一文件被两个进程同时 save 有极小概率撞名，撞名时会自动加 `_2` 而不是覆盖。
- `watch` 是轮询实现（默认 1 秒），不依赖 inotify，跨平台一致；大仓库可调 `--interval`。

## Roadmap

- [x] 通用 skill + 各工具规则模板 + 一键安装器
- [x] MCP 服务（save / list / restore / diff）
- [ ] `versave gc` 按总占用空间清理
- [ ] 版本备注导出成 `CHANGELOG.md`
- [ ] 与 docx/xlsx 的元数据（作者、修订号）联动
- [ ] 单文件二进制打包（无需 Python）

## License

MIT
