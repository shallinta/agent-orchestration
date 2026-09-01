# Microsoft Agent Framework 与本项目的边界对照

调研日期：2026-09-01

性质：外部项目调研，不属于 Stargazing 编号序列，不是技术选型或架构决策

结论：Microsoft Agent Framework 比 AutoGen 更接近本项目所需的部分底层能力，值得作为候选依赖和重要参考继续验证；但它仍不是本项目想做的 Harness，也不能直接替代本项目的产品与协作事实层

证据范围：Microsoft Agent Framework 官方仓库与 Microsoft Learn 当前文档；仓库 HEAD 为 `e2f7db207cb6cfc8a0d2babde4b40b4327b3c269`；未安装框架、运行示例或验证 Codex CLI / Claude Code CLI 适配

## 调研问题

这次调研回答四个问题：

1. AutoGen 官方推荐的 Microsoft Agent Framework 当前是什么；
2. 它是否已经提供本项目所需的外部成熟 Agent 编排、连续会话和长期协作能力；
3. 它与本项目都使用的“Harness”一词是否表达同一个概念；
4. 应当把它视为直接替代品、候选底层组件，还是仅作参考。

## 摘要结论

Microsoft Agent Framework（下文简称 MAF）是微软当前用于构建、编排和部署生产级 Agent 与多 Agent 工作流的统一框架，也是 AutoGen 与 Semantic Kernel 相关经验汇合后的后续方向。与进入维护模式的 AutoGen 相比，MAF 的持续发展状态、统一 Agent 接口、Agent service、会话、工作流检查点、HITL、Durable Extension、托管协议和可观测性明显更符合新项目评估条件。

它与本项目最重要的交集不是“也能让几个模型互相聊天”，而是：MAF 已经把应用自建 Agent、服务托管的成熟 Agent、远程 A2A Agent 都放到统一运行接口后面。官方列出的 Agent service 包括 GitHub Copilot coding-agent runtime、Anthropic Claude Agent SDK 和 A2A 远程 Agent；这些服务可以自行拥有 session、权限、内置工具和执行生命周期。这比 AutoGen 主要由开发者自行组合模型与工具的方式，更接近本项目“编排已有完整 Agent 产品”的出发点。

但 MAF 的核心仍是一个开发框架，不是本项目定义的协作产品。官方能力中没有直接对应以下完整产品语义：平台用户维护的身份卡、thread 内角色与系统标签、唯一主持和主管理员、权威目标确认、独立持久委托、结果吸收责任、完整 thread 事实、用户 Channel 分发、角色停用、三项正交自治约束。MAF 可以承载其中一些实现片段，但这些事实及规则仍需要本项目拥有。

因此，当前最合理的判断是：

- **作为整个 Harness 的直接替代品：不成立。** 产品边界和核心领域事实并不相同。
- **作为选定底层能力的候选依赖：有条件值得验证。** 尤其是 Agent service 统一接口、A2A、session、workflow checkpoint、HITL、middleware / hook、MCP 和 observability。
- **作为当前已选定底座：证据不足。** 尚未验证 Codex CLI、Claude Code CLI、本地长期运行、故障语义、取消和强制约束覆盖。

## MAF 当前的官方能力版图

### 1. 统一 Agent 抽象

MAF 用统一的 Agent 接口覆盖三类对象：应用基于模型推理构建的 Agent、自定义 Agent，以及由远程或托管运行时拥有执行生命周期的 Agent service。Agent 可以带 instructions、tools、middleware、context provider 和 `AgentSession`，并通过统一的 run / streaming 接口被调用。

这个抽象对本项目有直接参考价值：未来“角色执行器”不一定需要知道底层是模型 API、远程服务还是本地程序。但统一接口只消除了调用表面的差异，并不会自动解决每种 Agent 的真实 session、取消、输出、权限和故障边界。

### 2. Agent service：最接近本项目接入目标的部分

官方把 Agent service 与普通模型 provider 明确区分：前者不是只提供推理，而是可以拥有 Agent 定义、工具、权限、session 或执行生命周期。当前官方列表包括：

- Microsoft Foundry；
- GitHub Copilot，拥有 coding-agent runtime、session、权限、shell / file / URL 能力和 MCP；
- Copilot Studio；
- Anthropic Claude，使用 Claude Agent SDK runtime，拥有 session、权限、内置工具和 MCP；
- A2A，连接远程、符合协议的 Agent，由远端拥有定义、工具、session、task 与执行。

这证明 MAF 的设计对象已经包含“完整 Agent 服务”，而不只是裸模型。GitHub Copilot 与 Claude Agent SDK 也说明成熟 coding Agent 可以被纳入统一 Agent 接口。

不过，当前官方资料中没有发现 Codex CLI 的一等适配器。Claude Agent SDK 集成也不能未经实验就等同于对用户机器上 Claude Code CLI 命令与 resume 语义的可靠适配。对于本项目明确优先的 Codex CLI 和 Claude Code CLI，仍应假定需要适配器或协议桥接，直到实验证明可以直接复用官方集成。

### 3. Session、历史与持久化

`AgentSession` 是单个 Agent 多次运行之间的会话状态容器。它可以保存本地状态、历史 provider 状态或远程服务的 conversation ID，也支持序列化后恢复。官方同时强调：session 与具体 Agent / provider 配置相关；生产托管并不自带一个通用持久 session store，应用需要选择或实现可靠存储，并负责用户或租户隔离。

这与本项目“同一 thread 角色保持一个逻辑连续 Agent session”的需求高度相关，但两者不应等同：

- MAF session 表示一个 Agent 的连续上下文；
- 本项目 role 是 thread 内协作参与者，还带身份、权限、系统标签、可用状态和工作责任；
- 本项目 thread 是全部角色与 Harness 事件的事实边界，不能由任一 AgentSession 代替。

MAF 的 session 抽象可以成为角色底层连续性的候选承载，但 thread 事实仍需单独维护。

### 4. Workflows 与多 Agent orchestration

MAF Workflows 通过 executor、edge、event 和 state 表达可检查的执行路径，支持顺序、并行、handoff、group chat 和 Magentic 等模式。它还支持 fan-out / fan-in、共享状态、流式事件和 Agent executor。

这些能力适合表达边界清楚、路径需要确定性和恢复性的局部流程。但本项目已经确认，不把通用 DAG、固定开发阶段或某种多角色讨论模式作为整个 thread 的产品语义。主持需要根据动态语义持续决定下一步，thread 也可以跨越多个权威目标。

因此 MAF workflow 更可能用于某些确定性子流程，例如审批请求、外部动作、固定评审流水线或恢复敏感的后台操作，而不是直接把整个 thread 编译成一张长期工作流图。这个判断仍需具体实验，不能仅凭文档确定。

### 5. HITL、检查点与长期运行

MAF Workflow 可以由 executor 向外部系统请求信息并等待响应；pending request 会进入 checkpoint，恢复时重新发出。官方也明确说明，普通 sequential、concurrent 和 group chat orchestration 不会自动在任意位置等待自由形式的人类输入，需要显式加入 request port 或自定义 workflow。

Workflow checkpoint 在 superstep 边界保存 executor 状态、待传消息、待处理请求 / 响应和共享状态。Durable Extension 进一步提供跨进程恢复、长时间等待、事件与 timer、分布式执行和可靠流式传输，并可在等待人类输入时不持续占用计算资源。

这些机制对本项目的审批等待、调用恢复和定时触发很有价值，但 MAF 的 HITL 仍主要是 workflow 内的 request / response 控制点；本项目允许真人用户角色异步收消息、晚回复或不回复，同时其他角色继续工作。二者存在交集但不是同一交互模型。

### 6. MCP、A2A 与访问协议

MAF 支持本地和远程 MCP 工具，并可以把 Agent 暴露成 MCP tool。A2A 则用于跨进程、服务、团队或组织边界发现和调用远程 Agent；远端通过 context ID 维护自己的会话，调用方只看到协议响应。

对本项目而言，两者可能承担不同方向：

- Harness MCP server 可把发消息、发布委托、查询 thread、申请审批等公共协作能力提供给 Agent；
- A2A 可作为未来远程 Agent 的标准接入边界；
- CLI Agent 仍需要本地进程与 session 适配，不能因为存在 A2A 就自动获得协议兼容性。

MAF 还支持 OpenAI-compatible endpoints、AG-UI、Telegram 等托管入口，但官方明确把路由、认证、授权、持久存储和应用策略留给宿主应用。这与本项目“核心不依赖某个 UI 或 Channel”的方向相容，同时也说明 MAF 不会替本项目完成平台账号与 thread 权限体系。

### 7. 权限、安全、预算与可观测性

MAF 提供 tool approval、middleware、Agent Hooks、OpenTelemetry 和实验性的 FIDES 信息流控制。这些是构建强制约束与运行证据的重要积木。

但官方安全文档明确采用共同责任模型：普通工具默认不要求用户批准；框架不会替应用设定输入 / 输出长度和请求频率限制，开发者需要自行配置审批、参数校验、路径边界、速率限制和成本保护。服务端托管工具的审批也可能遵循各 provider 自己的机制。

因此不能把“MAF 支持 approval / security”直接写成“本项目的角色权限、审批策略和资源预算已经解决”。本项目仍需逐项标注哪些限制由本地 Harness 强制、哪些由远程 Agent 或服务强制、哪些只是 prompt 弱约束、哪些尚未覆盖。

## “Agent Harness”不是本项目的 Harness

MAF 官方也使用 `Harness Agent` / `Agent Harness` 一词，但它描述的是把一个 chat client 补成可长时间完成复杂任务的 Agent 运行脚手架：规划与执行模式、todo、上下文压缩、文件记忆与访问、工具审批和多步循环。

本项目的 Harness 则不负责把裸模型补成通用 Agent，而是连接多个已经具备 Agent 循环的产品与真人角色，维护 thread 协作事实并执行确定性通信、治理和调度规则。

可以用一句话区分：

- **MAF Agent Harness：让一个模型成为更完整的执行型 Agent；**
- **本项目 Harness：让多个既有 Agent 与真人成为可治理的长期协作者。**

MAF Harness Agent 对未来“自行开发一个内置主持 Agent”可能有价值，但不应因名称相同就把它当成本项目核心的现成实现。

## 与 AutoGen 的对照

| 维度 | AutoGen | Microsoft Agent Framework | 对本项目的影响 |
| --- | --- | --- | --- |
| 官方状态 | 维护模式，官方建议新项目迁移 | 当前微软主推的生产级统一框架 | MAF 才值得进入新依赖候选评估 |
| 主要对象 | 开发者组合模型、工具和 Agent team | 自建 Agent、远程 Agent service、workflow、hosting | MAF 更接近“编排完整 Agent” |
| 成熟 coding Agent | 主要依赖自定义 Agent 包装 | 官方接入 GitHub Copilot 与 Claude Agent SDK | 降低部分适配不确定性，但未覆盖 Codex CLI |
| 会话 | Agent / team state，自行持久化 | 统一 AgentSession、service session、history provider | MAF 的连续性基础更系统，但仍不是 thread |
| 长期运行 | 保存 / 恢复能力有限且有运行中一致性警告 | workflow checkpoint 与 Durable Extension | MAF 更适合恢复实验 |
| 人类参与 | UserProxy 等会阻塞 team 的典型模式 | request / response HITL，可持久等待 | MAF 更强，但仍不同于异步用户角色 Channel |
| 远程互操作 | 分布式 runtime / 自定义集成 | A2A、hosting、Agent service | MAF 更接近开放接入层 |
| 治理与产品事实 | 需应用自行建设 | 仍需应用自行建设，提供更多拦截积木 | 两者都不能替代本项目产品核心 |

## 与当前产品认识逐项对照

| 本项目核心认识 | MAF 覆盖程度 | 当前判断 |
| --- | --- | --- |
| 接入已有完整 Agent | 部分直接覆盖 | GitHub Copilot、Claude Agent SDK、A2A 很相关；Codex CLI、Claude Code CLI 仍待验证 |
| 一个角色保持连续逻辑上下文 | 部分覆盖 | AgentSession 是候选基础，但角色不只是 session |
| 持久 thread 与完整事实 | 未直接覆盖 | workflow state、history、trace 都不能自动成为 thread 权威事实源 |
| 身份卡、角色与系统标签 | 未覆盖 | 需要本项目产品层定义 |
| 权威目标与治理行为 | 未覆盖 | 不能由 workflow completion 或自然语言推断替代 |
| 独立、持久、单负责人委托 | 未发现对应核心实体 | A2A task、workflow step、agent-as-tool 都不等同于委托责任 |
| 主持语义推进 | 部分可表达 | Magentic / handoff 有参考价值，但不是本项目主持职责的完整实现 |
| 真人异步参与与 Channel | 部分覆盖 | HITL、AG-UI、Telegram 提供积木；用户角色语义与消息规则仍需建设 |
| 审批、权限和预算 | 部分覆盖 | tool approval / hook 可强制部分边界；角色权限和 thread 预算仍由本项目负责 |
| 定时、恢复与长等待 | 较强候选 | Durable Extension 很有价值，但可能引入 Azure Durable Task 依赖与运行复杂度 |
| UI 解耦 | 方向一致 | hosting protocol 可选，但平台账号、授权和事实存储由应用承担 |

## 当前建议

### 不把 MAF 直接宣布为 Harness 底座

MAF 已经足够重要，不能像 AutoGen 一样仅作为历史参考略过；但资料调研还不足以支撑底座决定。直接采用会提前引入 MAF 的语言生态、AgentSession 和 workflow 抽象，也可能诱导我们把 thread 错建模成 workflow、把角色错建模成 AgentSession，或者把 MAF Harness Agent 与本项目 Harness 混为一谈。

### 把它拆成若干可证伪的候选能力

如果后续由用户批准进入具体可行性实验，优先验证的不是“MAF demo 能否运行”，而是：

1. 能否用同一应用稳定接入一个官方 Agent service 与一个自定义 CLI Agent，并保持各自连续 session；
2. MAF 的自定义 Agent 接口是否会简化 Codex CLI / Claude Code CLI 适配，还是只增加一层包装；
3. Agent 调用 Harness MCP tools 时，结构化消息、委托和审批能否被可靠传递并保持应用拥有事实；
4. workflow checkpoint 与 AgentSession 能否在进程中断后恢复，而不重复已经产生外部副作用；
5. tool approval / middleware / hooks 的强制边界覆盖到哪里，provider 原生工具是否绕开本地控制；
6. 不使用 Azure Durable Extension 时，本地优先的运行方式能获得多强的持久与恢复保证；使用它时又会引入什么云平台约束。

这类实验若进入 Stargazing，应作为用户另行确认的具体项目记录；本文仍只是一份外部资料对照。

## 结论限制

- 本次只核实官方资料和仓库 HEAD，没有运行 MAF，因此不评价安装体积、性能、稳定性、开发体验或跨语言一致性；
- MAF 各语言和扩展的成熟度并不完全一致，文档中仍存在 prerelease、experimental 或“即将支持”的能力，后续实验必须固定语言、包版本和运行环境；
- “未发现 Codex CLI 一等适配器”只表示本次查阅的官方 Agent service、provider 与集成文档中没有该项，不证明社区或未来版本不存在；
- Claude Agent SDK 与 Claude Code CLI 的产品、认证、session 和权限边界不能仅凭名称推定相同；
- Durable Extension 的能力描述来自官方文档，尚未验证本地自托管时的真实运维成本和恢复语义；
- 当前建议不会修改 Dreaming 产品共识，也不构成技术选型决定。

## 主要官方资料

- [Microsoft Agent Framework 官方仓库](https://github.com/microsoft/agent-framework)
- [Agent Framework 核心概念](https://learn.microsoft.com/en-us/agent-framework/concepts/)
- [Agent concepts：统一 Agent、远程 Agent 与 session](https://learn.microsoft.com/en-us/agent-framework/concepts/agents/)
- [Agent services：GitHub Copilot、Claude Agent SDK 与 A2A](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/agent-services/)
- [GitHub Copilot Agent：session、权限、内置工具与 MCP](https://learn.microsoft.com/en-us/agent-framework/agents/providers/github-copilot)
- [Anthropic provider 与 Claude Agent SDK](https://learn.microsoft.com/en-us/agent-framework/agents/providers/anthropic)
- [Conversations & Memory](https://learn.microsoft.com/en-us/agent-framework/agents/conversations/)
- [Storage：session、history 与恢复](https://learn.microsoft.com/en-us/agent-framework/agents/conversations/storage)
- [Workflow concepts](https://learn.microsoft.com/en-us/agent-framework/concepts/workflows/)
- [Workflow orchestrations](https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/)
- [Human-in-the-loop](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop)
- [Workflow checkpoints](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints)
- [Durable Extension](https://learn.microsoft.com/en-us/agent-framework/integrations/durable-extension)
- [A2A：跨边界 Agent 通信](https://learn.microsoft.com/en-us/agent-framework/journey/agent-to-agent)
- [A2A hosting](https://learn.microsoft.com/en-us/agent-framework/hosting/agent-to-agent)
- [Self-hosting：协议、session store 与应用责任](https://learn.microsoft.com/en-us/agent-framework/hosting/self-hosting)
- [MCP tools](https://learn.microsoft.com/en-us/agent-framework/agents/tools/local-mcp-tools)
- [Agent Safety：审批与资源限制责任](https://learn.microsoft.com/en-us/agent-framework/agents/safety)
- [Agent Harness：MAF 对该术语的定义](https://learn.microsoft.com/en-us/agent-framework/get-started/harness)
- [从 AutoGen 迁移到 Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/)
