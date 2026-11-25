# 文件版本规则

本仓库交付文件的版本命名统一交给 versave，禁止手工添加 `_v2` / `_final` / `_副本` 等后缀。

每次修改文件后运行：

```bash
versave save <file> -m "<改动说明>" --json
```

未安装时：`python versave/versave.py save ...`

- 常规修改自动小版本 +1；结构性重写或定稿加 `--major`；用户指定用 `--set 3.1`
- 返回 `skipped: true` 表示内容未变，不要重试
- 查看历史 `versave list <file>`，回滚 `versave restore <file> -v 1.2`
- 不要自动删除历史版本
