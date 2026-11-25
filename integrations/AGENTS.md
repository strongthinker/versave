# 文件版本规则（versave）

本项目所有交付文件（.md / .txt / .py / .csv / .json …）的版本由 versave 统一命名，**不要手工给文件名加
`_v2`、`_final`、`_new`、`_副本` 之类的后缀**。

## 每次改动后立即执行

```bash
versave save <file> -m "<一句话说明这次改了什么>" --json
```

没有 `versave` 命令时，用项目内的脚本：

```bash
python versave/versave.py save <file> -m "<说明>" --json
```

- 普通修改 → 不加参数，小版本自动 +1（1.2 → 1.3）
- 结构性重写 / 定稿 → 加 `--major`（1.3 → 2.0，小版本归零）
- 用户指定版本号 → `--set 3.1`
- 返回 `"skipped": true` → 内容与上一版一致，不要重试

## 常用

```bash
versave list <file> --json               # 历史
versave restore <file> -v 1.2            # 回滚（回滚前自动存档）
versave diff <file> --from 1.1 --to 1.2  # 对比
```

## 底线

- 编辑的永远是原文件，不要把快照当工作文件继续改
- 不自动 `prune`、不擅自删除历史版本
- 交付回复里写清：工作文件 + 本次快照文件名 + 版本号
- 完全无法执行命令时，按 `名字_v1.0_YYYYMMDD_HHMMSS.ext` 手工命名，之后小版本递增，并附一张迷你版本表
