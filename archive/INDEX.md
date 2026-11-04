# 历史记录

这里是已经结束的过程材料，路径保持归档前的相对位置。当前规则以 [知识入口](../docs/INDEX.md) 为准。

| 记录 | 内容 |
|---|---|
| [会话与窗格设计稿](docs/session-restore-design.md) | 2026-09-07、提交 `9f2d0b6` 上的实现前设计。行号不是现行代码位置 |
| [子方案 A–E](docs/sub/A-session-and-close-confirm.md) | 同一基线上的分册。入口是 A，B–E 在同一目录 |
| [2026-10-15 审查](docs/reviews/review-2026-10-15.md) | 按模块分路的审查和方案。发现稿保持原样 |
| [需求编号与测试对照](dev/plans/requirement-coverage.md) | 需求编号与现有测试的对照 |

2026-09-07 的设计稿保留当时的方案，其中的行号不是现行代码位置。需求对照说明编号怎样对上当时的测试。现行行为看 `docs/`。

用 `archive <路径> --apply --expect <plan_sha256> --summary "<一行说明>"` 归档时，工具会在这张表的末尾加一行。
