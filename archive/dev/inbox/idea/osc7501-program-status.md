# 跟进 OSC 7501 Program Status Protocol

状态：已完成。来源：[终端对接 agent harness 的调研](../../../../dev/research/agent-harness-integration.md)，2026-11-06，agent:cursor。

## 观察到的事实

- OSC 7501 让程序在输出流里报告 `idle`、`working`、`blocked`、`done`、`error`，规范 rev 0.4（2026-10-10）。
- Codex、OpenCode 2、Qwen Code 不探测就发送，所以 TerminatorX 现在已经在收这些序列；VTE 不认识，默默丢弃。Claude Code 先发 `OSC 7501;?` 探测，终端不回应就不发。
- iTerm2 3.7.5、Kitty 0.50.0、cmux 已显示；Ghostty 1.4.0 解析但不显示；tmux 丢弃。
- VTE 上游 master（2026-10-31）没有实现 7501，也没有把未登记的 OSC 交给嵌入程序的通道。嵌入程序无法自己回应探测。

## 推测

- 不改 VTE 就要在 shell 和 VTE 之间插一个中继，自己解析输出流并回应探测。这会影响 `tcgetpgrp` 前台进程探测、`/proc` 工作目录探测、关闭确认和会话恢复，代价大，不建议现在做。
- 更稳妥的路线是向 VTE 上游提需求，由 VTE 解析 7501 并以 termprop 暴露、代为回应探测。在那之前，让 [agent-attention-bell](agent-attention-bell.md) 和 [agent-state-dbus](agent-state-dbus.md) 的状态模型直接采用 7501 的状态集合，以后接入时不用改模型。
- 7501 还在 0.x 修订中，状态集合可能变化。

## 怎样核实

- 在 GNOME GitLab 上搜 VTE 是否已有 OSC 7501 的 issue 或 MR。
- 每隔一段时间看 [areweosc7501yet](https://areweosc7501yet.com/) 和规范修订。

## 去向

不单独立项。TX-11 的状态名直接使用 `idle`、`working`、`blocked`、`done`、`error`、`clear`。不解析 OSC 7501，也不在 shell 和 VTE 之间加中继。跟进 VTE 上游仍见调研里的未证实项。
