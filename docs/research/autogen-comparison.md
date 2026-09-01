# AutoGen 与本项目的边界对照

日期：2026-09-01

状态：完成官方资料对照

性质：外部项目调研，不属于 Stargazing 编号序列，不是技术选型决策

结论：AutoGen 对本项目具有重要的设计参考价值，但不是同一产品，也不宜作为当前 Harness 的核心底座

证据范围：AutoGen 官方仓库主分支与 stable 文档；未运行 AutoGen 代码或原型实验

仓库参考修订：`027ecf0a379bcc1d09956d46d12d44a3ad9cee14`（于 2026-09-01 通过官方仓库 `HEAD` 核实）

## 要回答的问题

1. AutoGen 当前究竟是什么，它解决的问题与本项目是否一致；
2. AutoGen 是否已经提供了本项目想要的核心能力，以至于可以直接采用或改造；
3. AutoGen 的哪些抽象经过实践验证，值得带入后续设计；
4. 哪些表面相似性会误导我们把两者当成同类产品。

## 结论摘要

AutoGen 是一套供开发者构建 Agent 与多 Agent 应用的分层框架。它提供消息路由、Agent 运行时与生命周期、多种 Team 模式、自定义 Agent、状态导出、MCP 工具、代码执行和可观测性。这些能力与 Harness 的一部分技术关切高度重合。

但两者的出发点不同：AutoGen 主要帮助开发者把模型、工具和自定义逻辑组成 Agent 应用；本项目则要编排 Codex CLI、Claude Code CLI 等已经自带 Agent 循环、会话、工具与执行环境的成熟产品，并把它们与真人角色放入持久的 thread 协作和治理之中。

因此，AutoGen 可以帮助我们理解底层运行机制，但不能直接替代本项目的 thread 事实、角色治理、委托责任、外部 Agent 适配和用户 Channel 交互。即使把 AutoGen 当成底层库，这些仍是本项目必须自行建立的主要部分。

同时，AutoGen 官方仓库已明确进入维护模式，新功能不再继续开发，项目转为社区维护；官方建议新项目使用 Microsoft Agent Framework。这使“直接以 AutoGen 为新项目核心依赖”成为一个高风险选择。

## AutoGen 当前的官方定位

AutoGen 官方将它定义为构建可自主行动或与人协作的多 Agent AI 应用的框架。当前架构分为三个主要层次：

- `Core`：事件驱动的消息传递、Agent 生命周期与本地/分布式运行时；
- `AgentChat`：更高层、更有偏好的 Agent 与 Team API，提供轮流、选择器、移交、图流程等协作模式；
- `Extensions`：模型客户端、MCP、代码执行器、gRPC 运行时等具体扩展。

AutoGen Studio 是基于 AgentChat 的低代码原型界面，支持团队编辑、Playground、组件 Gallery 和导出部署。官方同时明确它不是生产级应用，认证、权限、安全和对抗性保护需要开发者自行建设。

## 逐项对照

| 对照维度 | AutoGen | 本项目 | 判断 |
| --- | --- | --- | --- |
| 主要用户 | 编写 Python/.NET 代码、构建 Agent 应用的开发者 | 希望编排现有成熟 Agent 与真人协作的平台用户 | 不同产品层级 |
| Agent 来源 | 通常由模型客户端、system message、工具、memory 和自定义代码组成 | 优先调用已拥有完整 Agent 循环和环境的 Codex CLI、Claude Code CLI 等产品 | 根本差异 |
| 参与单位 | 运行时中的 Agent ID，AgentChat 中的 Agent/Team | 身份卡实例化后、只属于 thread 的角色 | 有类似性，但角色还承载治理与渠道语义 |
| 协作容器 | 一次 `run()`/`run_stream()` 及其可保留内部状态的 Team | 可跨多个权威目标、长期保留的 thread | Team 不等于 thread |
| 推进方式 | RoundRobin、SelectorGroupChat、Swarm/Handoff、Magentic-One、GraphFlow 等预设或结构化模式 | 由唯一主持角色根据当前事实语义判断，Harness 执行确定性路由与约束 | 可用 AutoGen 模式做实验，不宜直接变成产品语义 |
| 消息 | Core 明确区分直接消息与 topic 广播，消息是可序列化数据 | Harness 负责定向、多选或全员分发并持久化所有消息 | 高度相关，值得重点借鉴 |
| 持续工作责任 | Handoff、task、自定义消息可表达工作转移，但官方核心语义中未提供本项目的持久委托实体与终态规则 | 委托独立于消息持续跟踪，有唯一发布者、唯一目标角色和不可重启终态 | 需由本项目自行建立 |
| 真人参与 | `UserProxyAgent` 可在 run 中阻塞等待输入，或终止 run 后在下一次 run 继续 | 用户身份卡实例化为长期角色，通过 Channel 异步收发，并可承载主管理员治理责任 | UserProxyAgent 不能直接表达本项目的真人模型 |
| 持久化与恢复 | Agent/Team 可 `save_state()`/`load_state()`，应用自行将状态字典写入文件或数据库；运行中保存可能不一致 | 完整 thread 记录是事实源，还要区分调用故障、未知结果、消息送达和委托状态 | AutoGen 状态能力只覆盖部分恢复问题 |
| 权限与治理 | 工具、执行器、Docker、取消条件等是应用构件；产品级认证、数据权限和安全由开发者建设 | 角色权限、审批策略和资源预算共同形成自治边界，并区分强制、弱约束与未覆盖 | 本项目的核心产品责任，AutoGen 不会代为提供 |
| 事实与知识 | Team 会话历史、model context 和 Memory 用于 Agent 上下文 | 完整记录是共同事实，快照、知识层和入场上下文是可追溯派生视图 | 存储对象和权威性语义不同 |
| UI | Studio 是低代码原型工具，官方明确不是生产级应用 | UI、Web、CLI 和消息 Channel 是同一 thread 的可替换访问入口 | Studio 可作交互参考，不能作为成品前端 |
| 项目维护 | 已进入维护模式，官方建议新项目转向 Microsoft Agent Framework | 新项目，尚未确定技术栈 | 不适合在无额外证据时建立长期核心依赖 |

## 最值得借鉴的部分

### 1. 分层而不强迫所有用户使用同一抽象层

AutoGen 把底层消息运行时、高层 Team 模式和供应商/工具扩展分开。这验证了一个对本项目重要的方向：Harness 的确定性事实与路由层不应和主持的语义策略、Agent 产品适配、UI 交互绑死在一起。

### 2. 消息是数据，直连与广播是不同契约

AutoGen Core 明确把消息定义为可序列化数据，并区分有返回值的直接请求/响应与无返回值的 topic 广播。这与本项目“Harness 不猜测自然语言意图、只处理明确契约”一致。但本项目还需要把消息送达与角色是否负有回复义务分开，不应把所有定向消息都模型成同步 RPC。

### 3. Agent 类型与实例标识分开

AutoGen Core 使用 Agent type 与 key 组成 Agent ID，运行时可以在首次送达消息时创建实例。它与“身份卡是可复用模板，加入 thread 后才产生角色”存在结构类似性。后续可借鉴其身份定址和工厂注册经验，但不应把 AutoGen Agent ID 直接等同于含治理语义的 thread 角色。

### 4. 自定义 Agent 与能力接口

AgentChat 允许实现 `BaseChatAgent` 的消息处理、重置、流式输出、保存与恢复等能力。这说明 AutoGen 并非只能使用内置 `AssistantAgent`；理论上可以编写自定义 Agent 去包装 CLI 或远程 Agent。但适配 Codex/Claude 的 session、输出、取消、超时和故障仍由我们自己实现，AutoGen 不会因为提供了接口就自动解决这些问题。

### 5. 状态恢复边界要由组件承担

AutoGen 的 Team 可聚合各 Agent 与 manager 的状态，但自定义 Agent 必须自行正确实现 pause、resume、save 与 load。官方还明确警告运行中保存 Team 可能得到不一致状态。这为 Stargazing 后续的恢复调研提供了重要反例：“有 `save_state`”不等于“已经具备可靠恢复”。

### 6. 结构化日志与 OpenTelemetry

AutoGen 同时区分人类阅读的 trace log 与可供系统处理的 structured event，并对 runtime、tool 和 AgentChat Agent 提供 OpenTelemetry 追踪。这对本项目“完整 thread 事实”与“运行可观测记录”的分层有参考价值：两者可以关联，但不能互相冒充。

## 不应直接照搬的部分

### 1. 不把 Team 当成 thread

AutoGen Team 的主要语义是运行一个 task，按某种 speaker selection 或图路径产生消息，然后在 termination condition 达成时停止。它可以保留内部历史并在下一次 run 继续，但这仍不是本项目中可跨多个权威目标、包含治理与完整事实的 thread。

### 2. 不把共享会话历史当成默认协作方式

SelectorGroupChat 依据参与者名称、描述和共享对话历史选择下一个发言者。本项目已确认默认不向所有角色广播全部消息，并通过定向消息、委托和权限受控查询来管理上下文。因此 GroupChat 只能是某些讨论的可选实验形式，不是 thread 默认通信模型。

### 3. 不把 UserProxyAgent 当成用户角色

AutoGen 官方明确指出，在 Team run 内调用 UserProxyAgent 会阻塞整个 Team，此时状态不稳定、不能保存或恢复，只建议用于短时即时交互。本项目需要的是用户可以晚回复或不回复、消息可发往外部 Channel、其他角色仍可继续推进的长期真人参与。这是不同的产品模型。

### 4. 不把 Handoff 或自然语言子任务当成委托

AutoGen 的 selector 和 handoff 非常适合控制对话中下一个说话者或控制权去向，但本项目的委托是独立持久化、可修改状态、有结果吸收责任且终态不可重启的工作责任。它不能由一次发言选择或一条 HandoffMessage 代替。

### 5. 不为了现成框架而内置固定 Team 模式

AutoGen 的 RoundRobin、SelectorGroupChat、Swarm 和 GraphFlow 对模式试验很有价值。但本项目已经明确，多角色讨论无需成为 Harness 特殊化的“协作活动”，也不内置软件开发阶段或通用 DAG。后续可以用这些模式做对照实验，但不应因库已提供就把它们升级为 Harness 的领域模型。

## AutoGen 能否作为 Harness 核心底座

当前结论：**不建议。**

这不是因为 AutoGen 能力弱，而是因为当前收益不足以抵消边界不匹配与长期维护风险：

1. AutoGen 已进入维护模式，官方的新项目建议已转向 Microsoft Agent Framework；
2. Codex CLI、Claude Code CLI 等外部成熟 Agent 仍需自定义适配，最困难的 session、输出、故障、取消和恢复问题不会被 AutoGen 自动消除；
3. thread、权威目标、系统标签、委托、审批、预算、用户 Channel 和完整事实仍需自行建设；
4. 分布式 runtime、GraphFlow 以及 Team pause/resume 等看似最有吸引力的部分在官方文档中仍标为实验性，且 pause/resume 的正确行为由自定义 Agent 负责；
5. 直接依赖它会提前引入 Python 运行时和 AutoGen 抽象，而本项目尚未通过真实 CLI 实验得到值得承担这一耦合的证据。

更合适的当前用法是：把 AutoGen 当作参考实现与对照组，在后续某个具体问题上借鉴或试验它的机制，而不是在还没有底层证据时把整个项目建立在其上。

## 对后续探索的参考价值

1. **不修改 Dreaming 核心边界。** AutoGen 没有证明本项目想解决的问题已经被完整解决，反而帮助明确了“构建 Agent”与“编排现有 Agent 参与持久协作”的差异。
2. **强化后续评估基线。** 对候选框架必须分别评估消息运行时、Agent 适配、完整事实、人类异步参与、治理约束和恢复保证，不能用“支持 multi-agent”一句话代替。
3. **单独调研 Microsoft Agent Framework。** 它是 AutoGen 官方指定的新项目方向，不对它进行单独核实，就不应将“AutoGen 不适合”扩展为“微软的 Agent 框架方向都不适合”。外部资料调研本身不进入 Stargazing；如果由此产生值得实证的具体假设，再由用户另行决定是否开展 Stargazing 实验。
4. **不急于运行 AutoGen 原型。** 资料已足以反对直接底座选型；只有后续出现具体假设，例如需要比较 topic 路由或 Team state 机制时，才值得编写可丢弃探针。

## 结论限制

- 本次是官方资料对照，没有安装或运行 AutoGen，因此不评价其实际性能、稳定性或开发体验；
- “不宜作核心底座”是基于当前产品边界与维护状态的建议，不是对 AutoGen 能力上限的否定；
- 本次没有证明 AutoGen 不能包装 Codex CLI 或 Claude Code CLI；它的自定义 Agent 扩展点在理论上允许这样做，但具体适配可靠性仍需实验；
- Microsoft Agent Framework 只在本文中作为官方继任方向出现，尚未对其做功能或适配性结论。

## 主要官方资料

- [AutoGen 官方仓库 README：分层架构、维护模式与继任方向](https://github.com/microsoft/autogen/blob/main/README.md)
- [AutoGen Core Application Stack：消息运行时与行为契约](https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/core-concepts/application-stack.html)
- [Agent Identity and Lifecycle：Agent type、key 与运行时实例](https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/core-concepts/agent-identity-and-lifecycle.html)
- [Message and Communication：直接消息与 topic 广播](https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/framework/message-and-communication.html)
- [AgentChat Agents：内置 Agent、状态与 model context](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/agents.html)
- [Custom Agents：自定义 Agent 扩展契约](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/custom-agents.html)
- [Selector Group Chat：基于角色描述和共享历史的发言选择](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/selector-group-chat.html)
- [Human-in-the-Loop：UserProxyAgent 与跨 run 反馈](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/human-in-the-loop.html)
- [AgentChat Teams API：pause、resume、save_state 与 load_state](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.teams.html)
- [GraphFlow：实验性图流程](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/graph-flow.html)
- [Distributed Agent Runtime：实验性分布式运行时](https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/framework/distributed-agent-runtime.html)
- [Workbench and MCP：MCP client 与共享工具状态](https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/components/workbench.html)
- [Logging 与 OpenTelemetry 支持](https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/framework/logging.html)
- [AutoGen Studio：原型 UI 定位与安全限制](https://microsoft.github.io/autogen/stable/user-guide/autogenstudio-user-guide/index.html)
- [AutoGen 到 Microsoft Agent Framework 迁移指南](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/)
