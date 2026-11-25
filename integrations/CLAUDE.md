# 文件版本规则（versave）

修改任何交付文件后，调用一次 versave，由它决定版本号，**不要自己拼 `_final` `_v2`**。

```bash
versave save <file> -m "<本次改动说明>" --json
```

- 已安装：`versave`；未安装：`python ~/.claude/skills/versave/versave.py save ...`
- 常规 → 小版本 +1；结构性重写/定稿 → `--major`；用户指定 → `--set 3.1`
- `skipped: true` = 内容没变，继续下一步，不要重试
- `list` / `restore -v 1.2` / `diff` 分别用于查历史、回滚、对比
- 回滚前工具会自动把当前内容存一版，所以误回滚可以再救回来
- 不自动 `prune`；不删除任何历史版本
- 交付时告知：工作文件 + 快照文件名 + 版本号
