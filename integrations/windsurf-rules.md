---
trigger: always_on
description: 修改文件后自动生成带版本号和时间戳的快照（versave）
---

# 文件版本规则（versave）

修改或新建交付文件后运行：

```bash
versave save <file> -m "<改动说明>" --json
```

未安装时用 `python versave/versave.py save ...`。

- 普通修改小版本 +1；结构重写/定稿加 `--major`；指定版本用 `--set 3.1`
- `skipped: true` 表示内容未变，不要重试
- 编辑原文件，不改快照；不手工加版本后缀；不自动删历史
- 交付回复写清：工作文件 + 快照名 + 版本号
