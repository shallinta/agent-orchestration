# Stargazing 观星日志

本文件是 Stargazing 的持续观星日志，按时间记录总体推进、重要变化、当前阻塞和下一步。单项证据与详细分析写入对应编号文档；这里不复制完整实验过程。

## 状态总览

| 编号 | 调研事项 | 状态 | 当前结论 |
| --- | --- | --- | --- |
| Stargazing 1 | AutoGen 与本项目的边界对照 | 已完成 | 有重要参考价值，不宜作当前核心底座 |
| Stargazing 2 | 环境与评估基线 | 待开始 | 未决 |
| Stargazing 3 | Codex CLI 程序化协作边界 | 待开始 | 未决 |
| Stargazing 4 | Claude Code CLI 程序化协作边界 | 待开始 | 未决 |
| Stargazing 5 | 异构 Agent 的共同接入边界 | 待开始 | 未决 |
| Stargazing 6 | Harness 公共协作能力通道 | 待开始 | 未决 |
| Stargazing 7 | 最小免人工中转连续闭环 | 待开始 | 未决 |
| Stargazing 8 | 持久化、进程重启与不确定结果 | 待开始 | 未决 |
| Stargazing 9 | 并发、取消、停用与保证强度 | 待开始 | 未决 |
| Stargazing 10 | 阶段综合结论 | 待开始 | 未决 |

## 2026-09-01：建立 Stargazing 与探索计划

用户明确下一阶段进行核心技术可行性探索，并选定 `Stargazing` 作为阶段名称。本次建立 `docs/stargazing/`，将探索按阻断性门槛组织，而不是按技术名词横向罗列。

当前计划优先验证 Codex CLI 与 Claude Code CLI 的程序化和连续交互边界，再验证 Harness 公共能力通道与双 Agent 连续闭环，最后研究重启恢复、并发取消和约束保证。选择这个顺序是为了尽早发现会使产品核心无法成立的问题。

本次只建立计划和记录规则，没有开始运行 CLI 实验，没有形成任何技术可行性结论，也没有决定技术栈、架构或 `v0.0.1` 范围。

当前下一步：由用户审阅并调整总计划；确认后从 Stargazing 2“环境与评估基线”开始。

## 2026-09-01：完成 Stargazing 1 AutoGen 对照调研

用户在整体计划尚可调整时，明确要求先调研 AutoGen 并与本项目对比。因此将该调研记为 Stargazing 1，原计划九项顺延为 Stargazing 2–10；这不表示其余计划已被整体确认。

官方资料显示，AutoGen 在消息契约、直连与广播路由、Agent 身份生命周期、可扩展自定义 Agent、Team 协作、状态导出和可观测性上具有很强的参考价值。但它的直接用户是构建 Agent 应用的开发者，主要抽象是模型驱动 Agent 和 Team run；本项目则要在持久 thread 中编排已成熟的外部 Agent 产品与真人角色，并维护目标、委托、治理、权限和完整事实。两者有底层机制重合，但不是同一产品。

更重要的当前事实是：AutoGen 已进入维护模式并转为社区维护，官方建议新项目使用 Microsoft Agent Framework。结合功能边界与维护状态，当前不建议把 AutoGen 选为 Harness 核心底座；可以把它作为设计参考和必要时的可丢弃实验对象。本次没有运行 AutoGen 代码，也没有证明其自定义 Agent 无法包装 CLI Agent；详细依据与限制见 `001-autogen-comparison.md`。

当前下一步：由用户讨论和质疑本次对照结论；未获明确指示前，不自动开始 Stargazing 2。
