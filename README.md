# Agent Orchestration

一个面向多 Agent 协作场景的编排 harness。它的首要目标不是再造一个 Agent，而是把 Codex CLI、Claude Code CLI 等已有 Agent 连接成可审计、可暂停、可恢复的协作流程，让用户从重复的任务分派、消息转发和进展整理中抽身，只在重要节点参与决策与签字。

## 当前阶段

项目处于立项和需求收敛阶段，计划从 `v0.0.1` 开始迭代。目前只建立项目记录与协作规则，尚未确定编程语言、运行时、存储方案或 UI 技术实现。

当前工作重点是找到一个足够小、但能真实验证价值的开发场景闭环。不会先设计一个大而全的通用多 Agent 平台。

## 长期愿景

- 用户可以配置 Agent 身份资料卡，包括名称、角色、性格、回复风格、发言权重、擅长方向、能力特征和调用方式。
- 支持 CLI Agent 和可远程调用的 Agent；CLI 方向优先预设 Codex CLI 与 Claude Code CLI。
- 每个需求使用独立的 thread 生命周期，由一个主 Agent 推进流程、拆分和分派任务、记录进展并协调其他 Agent。
- Harness 负责 Agent 间通信、结构化消息解析、外部动作执行、并发控制、检查点、定时任务和持久化。
- 用户作为高权重的特殊参与者加入 thread，并在关键决策点保留最终控制权。
- 核心执行逻辑与前端 UI 解耦，通过稳定协议连接 Electrobun、Web、飞书、Telegram 等不同界面或渠道。
- 在一个 thread 内形成可交付的经验、知识和业务资料；跨 thread、跨项目管理属于未来可能的相邻产品。
- 未来可扩展到内容创作、数据分析、金融研究等非代码协作场景。

## 近期明确不做

- 不接入桌面 App 类 Agent。
- 不在第一版实现前端 UI。
- 不先实现通用 DAG、复杂脑暴机制或自动 Agent 匹配算法。
- 不在价值闭环得到验证前建设跨 thread 知识库、分布式调度或多租户系统。
- 不默认执行提交、推送、创建 PR、部署等不可逆或外部可见动作。

## 项目记录

- [Dreaming 索引](docs/dreaming/README.md)：从核心问题到未来可能需求的阶段性思想成果。
- [项目手记](CHANGELOG.md)：持续记录想法、方案、实现和方向变化。
- [立项记录](docs/project-log/2026-08-12-inception.md)：保存项目起点、核心痛点和最初设想。
- [延后设计线索](docs/project-log/deferred-design-ideas.md)：保存讨论中出现但尚未进入设计阶段的实现方向。
- [未来相邻产品想法](docs/project-log/future-product-ideas.md)：保存不属于当前 Harness 职责的独立产品方向。
- [架构与产品决策](docs/decisions/README.md)：记录经过讨论并确认的重要决定。
