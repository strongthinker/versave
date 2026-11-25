# 文件版本规则（versave）

修改或新建交付文件后，执行：

```bash
versave save <file> -m "<改动说明>" --json
```

未安装时用 `python versave/versave.py save ...`。

- 普通修改：小版本 +1；结构性重写/定稿：`--major`；指定版本：`--set 3.1`
- 返回 `skipped: true` 表示内容没变，不要重试
- 不要手工加版本后缀，不要自动清理历史
- 交付回复中写明：工作文件、快照文件名、版本号
- 无法执行命令时：按 `名字_v1.0_YYYYMMDD_HHMMSS.ext` 命名，后续小版本递增
