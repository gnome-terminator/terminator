# 待处理项

还没决定要不要做、或者还没核实的问题，一条文件放在类型子目录里，例如 `dev/inbox/bug/<主题>.md`。不要写进 `docs/`，也不要另起一套目录。

每条写状态、来源、观察到的事实、还不能确定的推测、怎样核实，以及最后去了哪里。状态写在标题下面第一行。写法见 `scripts/wiki/formats.md`。

处理完时写明去向：转成了哪份计划、写回了哪篇知识、和哪条重复，或者为什么不做。状态改为「已完成」，再用 `python3 scripts/wiki/wiki.py archive <路径> --root .` 预览并归档。

还没决定的是 [重开时是否恢复 agent 会话](question/agent-session-resume.md)。其余四条已经完成并归档，结论在 [调研](../research/agent-harness-integration.md#可选方向)。这条也处理完后，再归档那份调研。
