# Stargazing 5：Harness 公共协作能力通道

日期：2026-09-03

状态：已完成

当前结论：有条件可行

性质：公共协作能力调用通道的技术可行性实验，不是正式协议、权限模型、生产服务或 Adapter 设计

## 要回答的问题

Codex CLI 与 Claude Code CLI 作为 thread 内 Agent 角色时，能否通过机器可解析、可归因且由 Harness 确定性校验的通道，使用`发消息`、`发布委托`和`查询 thread`等 Harness 公共协作能力，而不要求 Harness 从自然语言中猜测 Agent 意图。

本项关注的是“Agent 怎样明确调用 Harness 能力，Harness 怎样知道谁在调用、调用什么、成功还是失败”。它不验证完整消息、委托、thread、权限或数据库模型，也不要求两种 Agent 使用完全相同的底层通道。

## 与 Stargazing 4 的关系

Stargazing 4 已确认“专用 Adapter + 最小共同事实边界”有条件可行。本项继续保留这一前提：

- Codex 与 Claude Code 的工具配置、调用事件和连续交互仍由各自专用 Adapter 解释；
- Harness 只接收经过归因的公共能力请求及其确定性处理结果；
- Agent 文本、自述成功和底层进程退出不能替代 Harness 自己的调用记录；
- 本项新出现的能力差异应作为 Adapter 条件公开，而不是为了统一而隐藏。

## 已知前提与边界

1. 最小兼容性坐标为 macOS `26.5.2`、`arm64`、Codex CLI `0.144.6`、Claude Code CLI `2.1.252`，实验开始前重新确认；
2. 用户已完成两个 CLI 的安装、登录和必要模型 / provider 配置，本项不读取或保存真实凭证；
3. 所有探针只操作人工构造的临时 thread、角色、消息和委托，不连接真实 UI、数据库、消息软件或外部业务系统；
4. 不执行 push、PR、发布、部署、通知、购买或其他真实外部副作用；
5. 可以编写可丢弃的最小 Harness 假服务与调用探针，但它们必须明确位于实验目录，不伪装成生产代码；
6. 调用者身份必须来自 Harness / Adapter 服务端保存的执行上下文映射、server instance 映射或随机且只映射一个角色的短期能力凭据，不能信任 Agent 在工具参数或普通环境变量中自行填写的`caller_role_id`；
7. 本项只验证调用边界可行性，不证明恶意 Agent 已被 OS、容器或网络层隔离，也不确定正式鉴权方案。

## 当前官方资料形成的待验证认识

截至 2026-09-03，当前官方资料与本机 help 表明：

- Codex CLI 支持本地 STDIO 与 Streamable HTTP MCP server，可为 server 配置环境变量、启动 / 工具超时、工具允许 / 拒绝范围和调用审批行为；`codex exec --json` 可输出 MCP tool call 等机器事件；
- Claude Code 支持本地 STDIO、远程 HTTP、SSE 和 WebSocket MCP server，`--mcp-config` 与`--strict-mcp-config`可为一次程序化运行显式限定 MCP server；stream-json 的 init 和工具事件可用于观察 server 是否加载及工具是否调用；
- 两种 Agent 都已经在 Stargazing 2、3 中证明能够执行受控本地工具，但这不自动证明它们能可靠调用本项的三个 Harness 公共能力，也不证明调用者身份绑定成立。

这些只是公开能力线索，必须经过本轮隔离实验后才能形成项目结论。

## 当前假设

### 假设一：本地 MCP tools 是当前最强的共同候选

为每个角色的 Agent 执行上下文配置 Harness MCP server 后，Agent 可以通过明确工具名和结构化参数调用三个最小公共能力，Harness 可以直接返回结构化成功或错误结果。两种 CLI 可以使用不同配置方式，但 Harness 不需要解析自然语言意图。

### 假设二：角色身份可以在工具参数之外绑定

实验 server 可以由专用 Adapter 以角色专属配置启动，把调用角色绑定在 Harness 已登记的 server instance、执行尝试或随机短期能力凭据上；工具参数不暴露调用者字段。普通 `ROLE_ID` 环境变量不是身份锚点，因为拥有 shell 的 Agent 可以改写它。这样 Harness 至少能确定“这个请求来自被配置为某角色的能力通道”，而不是相信模型自报身份。

这只证明通道级归因可行，不证明同一系统用户下的恶意 Agent 无法绕开入口、读取其他进程信息或窃取凭据；更强隔离留待后续保证强度研究。

### 假设三：CLI 与本地 HTTP 可以作为可行但较弱的替代通道

当 Agent 已拥有 shell / command 工具时，可以调用 Harness 提供的专用 CLI，或访问 loopback HTTP endpoint。调用者身份必须由随机且仅映射到一个角色的短期能力凭据绑定，而不是由 wrapper 名称、普通 role id 环境变量或 Agent 可选命令参数决定。Agent 即使改写或删除自身凭据也只能使请求失效，不能因此成为另一个角色；是否能窃取另一角色凭据不在本项保证范围。

它们的弱点可能是：必须向 Agent 开放更宽的命令执行能力；CLI 进程启动开销和 HTTP 服务生命周期需要额外管理；Agent 可能接触其自身能力凭据；不同平台的 shell 与网络策略也会影响成立条件。

### 假设四：Agent 返回结构化工具请求是可解析但更弱的路径

Harness 可以要求 Agent 最终输出符合 schema 的“能力请求”，在本次 Agent 调用结束后解析、校验并执行，再通过后续输入把结果交还 Agent。这可以避免开放 shell 或 MCP，但不是原生同一 turn 工具调用，增加往返、session 恢复和结果关联要求。

调用者身份仍应由产生该输出的执行尝试绑定，不能使用模型输出中的身份字段；schema 只能约束形状，不能保证 Agent 一定选择正确能力或参数。

### 假设五：权限判断和事实写入必须发生在 Harness 侧

无论使用哪种通道，Agent 只负责发出明确请求。目标角色是否存在、当前调用角色能否发布委托、参数是否合法、写入是否成功，都由实验 Harness 固定逻辑判断并留下事实记录。Agent 收到的成功或失败结果必须能与服务端记录对照。

## 反证条件

出现以下任一情况时，应收缩或否定相应假设：

1. 某个 Agent 只能用自然语言描述“请 Harness 发消息”，无法产生机器可识别的能力调用；
2. Harness 必须让模型在参数中自报调用者身份，且没有外部执行上下文能够绑定真实角色；
3. Agent 收到成功结果，但实验 Harness 没有相应事实记录，或 Harness 已拒绝而 Agent / Adapter 把调用报告为成功；
4. 无效参数、无权限或未知目标无法以明确错误返回，迫使 Harness 或 Adapter 解析自然语言判断；
5. 同一 Agent 的两个公共能力请求无法与各自执行尝试和结果相关联；
6. 配置的 MCP server 未加载或工具不可见，却不能从机器输出中发现；
7. 本地 CLI / HTTP 路径只能通过把可任意伪造的 caller id 当作普通参数来归因；
8. 结构化请求路径无法在保持 session 连续性的情况下把执行结果可靠送回 Agent；
9. 为了让任一路径可用，必须修改真实用户全局配置、开放危险权限或接触真实凭证。

## 各通道的身份锚点

| 通道 | 本项身份锚点 | 不可信输入 | 身份改写检查 |
| --- | --- | --- | --- |
| MCP | Adapter 为执行尝试登记的角色专属 MCP server instance；server instance 只映射一个角色 | 工具参数中的 caller / role 字段 | 调用时额外注入`caller_role_id`，预期 schema / server 拒绝，或服务端仍只归因已登记角色 |
| 专用 CLI | Harness 创建的随机、短期、单角色 capability；服务端只保存 capability 到角色的映射 | 命令参数、普通 role id 环境变量、Agent 自述 | 使用伪造 caller 参数或无效 capability，预期拒绝且不能改变归因 |
| loopback HTTP | `Authorization`承载的随机、短期、单角色 capability；只在短命服务存活期间有效 | JSON body、query 中的 caller / role 字段 | body 注入其他角色 id，预期拒绝或忽略；无效 capability 返回未授权 |
| 结构化返回请求 | Adapter 已知的 execution-attempt 到角色映射；请求 schema 不含 caller 字段 | 模型输出中的 caller / role 字段 | 输出额外身份字段时 schema 校验失败，不能改变 driver 绑定角色 |

以上只验证 Harness 提供入口内部的确定性归因，不证明同一 OS 用户下的恶意 Agent 已被隔离，也不阻止 Agent 使用未覆盖的原生工具绕开 Harness。

## 验证方法与计划证据

### Probe 5.0：当前命令与官方表面

- 重新确认四项最小兼容性坐标；
- 读取 Codex 与 Claude Code 当前 MCP、程序化输出和工具限定相关 help；
- 对照当前官方 MCP 文档，记录公开支持与本机实际参数的差异；
- 不修改用户全局 MCP 配置。

### Probe 5.1：可丢弃的最小 Harness 假服务

在项目内明确的实验目录建立最小探针，只包含人工 thread 事实和三个能力：

- `query_thread`：读取固定的人工 thread 摘要；
- `send_message`：向已存在的人工目标角色写入一条消息记录；
- `publish_delegation`：由一个 Agent 角色向唯一 Agent 目标角色写入一条委托记录。

所有能力都不接受调用者 id 参数；调用者来自 server instance、execution attempt 或 capability 的 Harness 侧映射。探针预定义三个稳定目标：

- `allowed-worker`：存在，当前调用角色有权向其发消息和发布委托；
- `forbidden-worker`：存在，但当前调用角色无权向其发布委托；
- `missing-worker`：不存在，用于产生 not-found 结果。

由此可以在不临时修改权限的情况下稳定区分未知目标、非法参数和无权限失败。探针把服务端观察与 request id 写入脱敏 JSONL，供结果对照。探针不是正式领域模型或持久化方案。

### Probe 5.2：本地 STDIO MCP tools

分别为 Codex 与 Claude Code 建立隔离临时 workspace 和角色专属 MCP server 配置：

1. Agent 查询人工 thread；
2. Agent 尝试向`missing-worker`调用并读取明确的 not-found；
3. Agent 尝试向已存在的`forbidden-worker`发布委托并读取明确的 forbidden；
4. Agent 注入或改写 caller id，验证 schema 拒绝或服务端仍归因原角色；
5. Agent 向`allowed-worker`发送人工消息；
6. Agent 向`allowed-worker`发布有权限的人工委托；
7. Agent 再次查询并返回摘要；
8. 对照 Agent 事件、MCP 返回与服务端 JSONL，确认调用顺序、调用角色、request id、参数、成功 / 失败和实际写入一致；
9. 使用一个无法启动的实验 MCP 配置，确认 server 未加载能够从机器输出识别，且没有能力写入。

实验 MCP server 只暴露三个 Harness tools；Agent 仍实际拥有的内置 shell、文件或其他工具必须从 init / 事件中记录，不能宣称总工具面只有三个。若当前 CLI 无法在不修改全局配置的情况下隔离加载，则暂停并记录限制。

### Probe 5.3：独立 CLI 与 loopback HTTP

在 MCP 结果明确后，用相同人工能力各做一条最小对照：

- CLI 路径只允许调用 Harness 专用命令，使用随机单角色 capability，不让 Agent自行提供 caller id；
- HTTP 路径只监听 loopback，使用角色范围的人工能力凭据，服务端只记录映射后的角色而不记录凭据值；
- 比较结构化结果、错误返回、身份绑定、工具开放面、服务生命周期和可移植性。

如果两条路径只是在已有 shell 能力之上重复证明同一事实，允许减少 Agent 调用并以现有工具执行证据加直接协议探针形成结论，但必须明确这是分析推断而非完整端到端实验。

### Probe 5.4：Agent 结构化返回请求

分别要求两个 Agent 按固定 schema 返回一个不含 caller id 的能力请求；Harness 实验 driver 以执行尝试绑定调用角色，校验并执行请求，再通过明确 session 后续输入返回工具结果。至少包含一个成功和一个因额外身份字段或非法参数而校验失败的样例。

本探针重点比较往返边界，不把模型生成的请求视为已经发生的工具调用，也不把 schema 合法等同于业务权限通过。

### Probe 5.5：归因与错误矩阵

综合四种通道，逐项记录：

- 调用者身份来自哪里，Agent 能否在普通参数中改写；
- Harness 侧是否先校验再写入；
- 请求、结果和服务端事实能否用执行尝试关联；
- 未知目标、非法参数、无权限、服务不可用和结果未知怎样表达；
- 需要开放的 Agent 原生工具范围；
- 哪些是 Harness 强制、外部机制强制、弱约束或未覆盖能力。

`结果未知`的公共能力恢复语义不在本项伪造验证，明确留给 Stargazing 7。本项只记录服务进程中断时现有证据能说明什么，不宣称已经解决不确定写入或重试安全。

## 通道证据对齐表

| 通道 | Agent E2E 范围 | 成功证据 | 失败证据 | 服务端事实 | 本项明确不测 |
| --- | --- | --- | --- | --- | --- |
| MCP | Codex、Claude Code；主验证；三个能力 | 三个能力实际调用并返回 | 未知目标、无权限、身份字段注入、server 未加载 | 每次请求的固定角色、request id、结果和写入 | 远程 MCP、OAuth、恶意同用户隔离、崩溃中不确定写入 |
| 专用 CLI | 两种 Agent 各做最小调用；不要求覆盖三个能力 | 至少一次查询或发送成功 | 无效 capability 或 caller 参数注入 | capability 映射角色及实际写入 | 跨平台 shell、CLI 安装分发、并发容量 |
| loopback HTTP | 两种 Agent 各做最小调用；允许在证据重复时缩为直接协议探针并明确降级 | bearer capability 下至少一次成功 | 无效 capability 或 body 身份注入 | capability 映射角色及实际写入 | TLS、远程网络、OAuth、端口暴露和生产服务生命周期 |
| 结构化返回请求 | 两种 Agent 各做一次请求生成与结果回送 | schema 合法请求被 driver 执行并在后续 session 收到结果 | 额外身份字段或非法参数校验失败 | execution-attempt 映射角色及执行记录 | 同 turn 原生工具体验、乱序并发、崩溃恢复 |

若后续基于证据削减某项 E2E，单项结论必须明确标为直接协议事实或分析推断，不能与 MCP 主验证证据等量表述。

## Agent 自述与 Harness 事实冲突检查

Stargazing 3 已有 Agent 在没有工具时用文本伪造工具成功的事实，证明 Agent 自述不能作为能力调用证据。本项不刻意诱导 Agent 欺骗，而是要求实验 driver：

1. 为每个能力请求生成或取得 request id，并关联 execution attempt；
2. 只根据 Harness 服务端记录判定请求是否接受、拒绝和写入；
3. 将 Agent 最终摘要与这些记录对照；
4. 若 Agent 声称被拒请求成功、遗漏实际调用或把未调用说成已调用，输出明确 mismatch，而不是修改服务端事实迁就文本。

若本轮没有自然出现冲突，只能证明对照机制存在并且本轮一致；不能声称已经穷尽所有冲突。

## 安全与停止规则

1. Agent 工作只接触人工数据、实验脚本和隔离 workspace；
2. 不读取或记录真实 token、账号、全局 MCP 配置内容或其他 thread 数据；
3. 不使用危险 bypass 权限，不访问公网服务，MCP 优先使用本地 STDIO；
4. HTTP 对照如执行，只绑定 loopback 并由 OS 分配端口 `0`，结束后检查进程退出；
5. 任何人工能力凭据仅在当次进程环境中存在，原始值不进入文档、日志或 Git；
6. 探针使用现有运行时和自包含实现，不在线安装 npm、pip 或其他依赖；缺少必要能力时先停止并记录；
7. Codex 已在 Stargazing 2 证明即使 ignore flags 仍可能读取 workspace 外 Skill 文件；当时的用户授权只适用于已经成文的 Stargazing 2 后续探针，本项不推定它自动延伸。Probe 5.0 与不启动 Agent 的 5.1 可继续；启动 Probe 5.2 Codex Agent 前必须取得用户针对本项的知情选择。若用户同意，本项仍只使用人工输入、不主动探测其他本地文件，也不把该选择写成强读取隔离；若出现新的、非预期 workspace 外读取或外部访问，立即停止后续 Agent 探针；
8. Claude Code 先沿用 Stargazing 3 验证过的 safe-mode / restricted 基线，只检查 init 与工具表；如果 MCP 配置要求放宽基线，必须先记录变化和实际工具面再启动工作调用；
9. 若 Agent 工具范围无法缩小到本轮所需能力，先记录并评估风险，不未经用户知情扩大；
10. 任何无法确认的副作用都停止后续同类探针并如实记录。

## 预定判断标准

核心门槛成立至少需要：

1. Codex 与 Claude Code 各自至少存在一条无需真人操作、机器可解析的 Harness 能力调用路径；
2. 调用角色由 Harness / Adapter 已知上下文绑定，不依赖 Agent 自报 caller id；
3. 三个最小能力至少在主验证通道中成功调用并产生可核对服务端事实；
4. 至少一个拒绝路径能被 Harness 确定性执行并以机器结果返回 Agent；
5. Agent 自述、Adapter 事件与 Harness 服务端事实能够按 execution attempt / request id 对照；出现冲突时以 Harness 事实为准并输出 mismatch，没有自然冲突时不宣称已经验证所有冲突形态；
6. 两种 Agent 不必采用相同底层通道，但差异和保证强度必须可公开；
7. 所有未验证的身份隔离、送达、幂等、重试和外部副作用范围如实保留。

若核心门槛成立，但身份绑定只在角色专属通道前提下可靠、配置或权限存在限制，结论为`有条件可行`；若任何路径都必须依赖自然语言意图识别或 Agent 自报身份，则为`不可行`；证据不足时为`未决`。

## 当前观察

### Probe 5.0：当前命令与官方表面

2026-09-03 重新查询得到：macOS `26.5.2`、`arm64`、Codex CLI `0.144.6`、Claude Code CLI `2.1.252`，与 Stargazing 4 的坐标一致。

本机 help 确认：

- Codex 提供`codex mcp add`，可添加 STDIO 或 Streamable HTTP server，并为 STDIO server 设置环境变量；`codex exec`仍提供逐次配置覆盖、JSONL、sandbox、ignore flags 和明确 session resume；
- Claude Code 提供`claude mcp add`和`--mcp-config` / `--strict-mcp-config`，支持 STDIO / HTTP / SSE 配置；程序化运行仍提供 stream-json、工具允许 / 拒绝、safe-mode、restricted、permission mode 和明确 session resume；
- 当前官方 Codex 文档还明确提供 MCP server 的`required`、启动 / 工具超时、工具 allow / deny 和审批配置；Claude Code 官方文档说明 strict MCP config 可以只加载显式传入的 server，并能在 stream-json init 的`mcp_server_errors`观察跳过的错误配置。

本轮仅读取公开 help 和官方资料，没有查看或修改两个 CLI 的用户全局 MCP 配置。Probe 5.0 支持继续建立本地 STDIO 假服务，但不能替代 Agent 实际调用证据。

### Probe 5.1：可丢弃的最小 Harness 假服务

已经在 [`experiments/stargazing-005/`](../../experiments/stargazing-005/README.md) 建立只依赖 Python 标准库的可丢弃实验服务。它只保存进程内人工事实，以 newline-delimited JSON-RPC 2.0 STDIO 提供最小 MCP 表面，并暴露`query_thread`、`send_message`和`publish_delegation`三个工具。

当前固定实验事实为：

- server instance 把调用者固定归因为`probe-caller`，请求 schema 不包含调用者字段；
- `allowed-worker`允许消息和委托，`forbidden-worker`存在但拒绝委托，`missing-worker`不存在；
- 所有请求先做 schema、目标存在性和权限判断，只有合法请求才改变内存中的消息或委托事实；
- 每次工具处理生成 Harness request id，工具结果与服务端 JSONL 可关联；日志只保留服务端枚举工具名、固定归因、结果和归一化布尔 / 计数事实，不保留消息、任务、身份注入值、任意未知工具名或任意目标字符串。

实现过程先出现两轮预期失败：第一轮因服务尚不存在而失败，第二轮揭示外层身份字段注入未被拒绝。独立质量审查随后又真实复现了日志脱敏假阳性：未知工具名和任意目标 id 曾可原样进入 JSONL。修复后新增泄露回归、协议错误、缺省 arguments、`ping`以及 text / structured result 一致性检查；真实客户端兼容修正后，MCP 部分完整复跑为`12 tests / 0 failures`，直接协议 smoke 也取得初始化、`ping`、工具列表、thread 查询及唯一 request id 对应的服务端事实。实验目录没有留下`__pycache__`等运行生成物。

Probe 5.1 由此证明：在一个固定单角色 server instance 内，三个最小能力可以由确定性代码校验、写入和审计，请求不能通过普通参数改变服务端归因；业务拒绝也可以作为结构化工具结果返回。它尚未证明两个不同 server instance 的动态角色映射、真实 Agent 能否加载和调用工具、恶意同系统用户隔离、完整 MCP 生命周期、崩溃一致性、送达、幂等或安全重试。实验声明 MCP `2025-03-26`；其中 text content 是本项的兼容事实，`structuredContent`作为同步对照保留，不将其在该版本下的扩展出现解释为普遍客户端保证。

独立运行前审查和 Probe 5.1 复审均确认：不启动 Agent 的实验可以成立；Agent E2E 仍有一项明确门禁。Stargazing 2 的既知 workspace 外读取风险不能沿用旧授权，启动 Probe 5.2 Codex Agent 前需要用户针对 Stargazing 5 作出知情选择。

用户于`2026-09-03`明确接受 Stargazing 5 人工样例中 Codex 仍可能读取临时 workspace 外本地 Skill 文件的既知风险，同意继续 Probe 5.2 及本项后续已成文实验，直到形成 Stargazing 5 结论。该选择不构成强读取隔离，不授权主动读取其他本地文件、访问外部服务或扩大真实副作用；若出现新的非预期 workspace 外读取或外部访问，仍按停止规则暂停相应探针。

截至记录该选择时，尚未启动 Codex 或 Claude Code 的公共能力 Agent 调用。

### Probe 5.2：本地 STDIO MCP tools

用户知情选择后，两个 Agent 都在人工数据和隔离临时 workspace 中完成了同一条七步调用序列：首次查询、向不存在角色发消息、向无权限角色发布委托、注入额外调用者字段、向允许角色发消息、向允许角色发布委托、再次查询。Harness 服务端事实最终均为一条合法消息和一条合法委托；每次工具结果中的 Harness request id 都能在服务端 JSONL 中找到唯一对应记录，固定调用者均为`probe-caller`。两个 Agent 的最终文字摘要与工具事件、结构化返回和服务端事实一致，但本轮一致只说明对照机制可工作，不代表 Agent 自述永远可靠。

Codex 使用临时逐次配置加载角色专属 STDIO server，实际事件为`mcp_tool_call`。`query_thread`、`send_message`和`publish_delegation`均成功被调用；不存在目标返回`not_found`，无权限返回`forbidden`，额外`caller_role_id`返回`invalid_params`且没有写入。最终查询显示`message_count=1`、`delegation_count=1`。首次故意配置不存在的 Python 路径时，`required=true`使 Codex 在 Agent turn 前以“required MCP servers failed to initialize”结束，没有发生能力写入。实验也暴露了真实兼容问题：当前 Codex 会在`tools/list`和`tools/call`参数中携带`_meta`；假服务最初拒绝这些客户端元数据，修正为只允许相应协议位置后才建立有效调用。该修正没有放宽 Agent 工具 arguments 的身份字段约束。

Claude Code 使用`--strict-mcp-config`只加载显式人工 server，并保留`--restricted`、`--tools ''`、`--disable-slash-commands`、`dontAsk`等约束；init 显示工具表只有三个`mcp__sg5__*`工具、server 状态为`connected`、plugins 为空。相同七步调用得到与 Codex 一致的 Harness 结果和最终计数。一个重要反例是：在本机当前版本中同时启用`--safe-mode`时，即使显式传入 MCP 配置，init 仍显示 tools 和 mcp_servers 均为空，因此本项必须移除 safe-mode 才能使用显式 MCP；这不是无代价兼容。故意把 server command 设为不存在路径时，Claude 仍进入 Agent turn，但 init 明确显示`sg5`状态为`failed`且工具表为空；Agent 如实报告未查询。可见两端都能机器识别服务不可用，但失败时机和进程结果语义不同：Codex 的必需服务失败阻止 turn，Claude 则允许无该工具的 turn 继续，不能只凭 CLI 退出码判断能力已加载。

以上真实 Agent 探针没有写入 workspace 文件，也没有访问公网业务服务；Claude 的最终文字曾概括其一般工具能力，但 init 事实仍以实际传入约束后列出的工具表为准。Codex 的 read-only sandbox 也不能扩大解释成 workspace 外强读取隔离，继续沿用用户已知情接受的 Stargazing 2 限制。

### Probe 5.3：专用 CLI 与 loopback HTTP 对照

同一个人工 Harness 内核增加了两条只依赖 Python 标准库的直接协议对照。为了可复现，探针使用公开、固定的人工 capability 模拟“单角色 capability”身份锚点，服务端 registry 只保存 capability 的 SHA-256 到固定角色的映射，日志不保留 capability 原文。它验证的是映射与拒绝语义，不是随机性、保密性、短期生命周期、轮换或撤销；正式候选必须使用足够高熵、短期且可撤销的 capability，单独保存低熵凭据的哈希并不构成安全保证。

- 专用 CLI 只从`SG5_CAPABILITY`环境变量取得能力凭据，不接受 caller / role 命令参数；有效凭据查询成功，无效凭据返回`unauthorized`和退出码 3，额外身份字段返回`invalid_params`和退出码 2；
- HTTP server factory 固定绑定`127.0.0.1`与 OS 分配的端口 0，只从`Authorization: Bearer`取得能力凭据；有效调用、无效凭据、body 身份注入和业务权限拒绝分别得到对应 HTTP 状态及结构化 Harness 结果；测试结束显式 shutdown、close 并确认线程退出；
- 两者都继续由 FakeHarness 判断参数、目标存在性、权限和写入，request id 可以关联到脱敏服务端事实；测试还确认人工 capability、无效 capability、消息正文和伪造角色不会进入日志。

直接 CLI smoke 的退出码为：成功 0、无效 capability 3、身份字段注入 2。包含 MCP、CLI、HTTP 和结构化 driver 的完整测试最终为`20 tests / 0 failures`（Probe 5.4 收缩 schema 后增加一项回归）。

本项依据预定削减规则，没有让 Codex 与 Claude Code 再分别重复调用 CLI 和 HTTP。Stargazing 2、3 已证明它们具备受控本地工具执行能力，因此“具备相应 Bash / shell 或 HTTP client 工具时可调用这两个入口”是合理分析推断；它不是本轮 Agent E2E 事实。相比 MCP，这两条路径要求额外开放命令执行或本地网络客户端，Agent 还会接触自身 capability，工具面与凭据管理责任更大，因此当前只能作为候选替代通道，不能与 MCP 主验证作等强度陈述。

### Probe 5.4：Agent 结构化返回请求

两个 Agent 都完成了“生成结构化请求—Harness driver 执行—把结果送回原 session”的真实往返。请求 schema 不包含 caller 或 execution attempt；driver 根据已登记 execution attempt 固定归因为`structured-probe-caller`，模型输出不能选择身份。

首次 Codex 尝试产生了有效失败证据：初版 schema 虽把顶层设为严格对象，却没有在`arguments`对象层显式设置`additionalProperties:false`，Codex 在模型调用前以`invalid_json_schema`拒绝。探针随后收缩为足以验证往返的唯一请求`query_thread + 空 arguments`，并在每个对象层显式禁止额外字段；这不是把产品公共能力收缩为只有查询。修正后：

- Codex 以结构化输出生成`{"tool":"query_thread","arguments":{}}`，没有调用工具；driver 执行后产生唯一 Harness request id 和固定角色服务端记录；同一 Codex session resume 后准确确认该 request id，并明确区分先前的“请求”与随后收到的“实际 Harness 结果”；
- Claude Code init 的工具表只有`StructuredOutput`，生成同义`structured_output`，同样由 driver 执行并记录；恢复同一 session 后准确确认另一个 Harness request id，并明确说先前输出不等于工具已经运行；
- 直接 driver 探针和回归测试还证明：顶层额外`caller_role_id`或超出本探针 schema 的请求被拒为`invalid_params`，不会按伪造身份调用能力。由于严格 schema 已阻止 Agent 生成此类形状，该失败样例是 driver 直接协议事实，不是模型自然产生的 E2E 失败。

这证明结构化返回请求可以作为机器可解析的备用边界，并能保持 session 连续性；代价是能力执行发生在 Agent turn 结束后，Harness 必须额外驱动下一次输入，交互至少多一次往返。Schema 合法只证明形状合法，业务权限仍由 Harness 判断。

### Probe 5.5：归因、错误与保证矩阵

| 通道 | 本轮 Agent 证据 | 调用者归因 | 失败可见性 | 额外开放面 / 生命周期 | 保证边界 |
| --- | --- | --- | --- | --- | --- |
| 本地 STDIO MCP | Codex、Claude Code 均完成三个能力及正反路径 | 角色专属 server instance 固定映射；工具参数无 caller | `not_found`、`forbidden`、`invalid_params`及 server 启动失败均机器可见，但两端失败时机不同 | 管理 server 配置、启动和客户端兼容；Claude 当前需移除 safe-mode | Harness 可强制参数、权限、写入与通道内归因；不保证同 OS 用户强隔离 |
| 专用 CLI | 直接协议测试；Agent 可调用性为既有 shell 证据上的推断 | 人工单角色 capability 的服务端映射；正式候选需高熵、短期、可撤销 | 结构化结果加约定退出码 | 必须开放专用命令或更宽 shell；每次进程启动 | capability 有效时可强制通道内归因；生成、保密、窃取防护和其他命令未覆盖 |
| loopback HTTP | 直接协议测试；未做本轮 Agent E2E | 人工 Bearer capability 的服务端映射；正式候选需高熵、短期、可撤销 | HTTP 状态加结构化结果 | 管理 loopback 服务、端口和 HTTP client | 只证明`127.0.0.1`短命服务内映射与拒绝；无 TLS、OAuth 或远程保证 |
| 结构化返回请求 | 两端均完成请求生成、driver 执行和原 session 结果回送 | execution attempt 的 driver 映射 | schema / driver 拒绝与 Harness 业务结果可分开 | 无需给 Agent MCP 或 shell，但需要 turn 后 driver 和再次输入 | Harness 可强制 schema、权限和归因；不能保证模型选择语义正确的请求 |

四条路径都不需要 Harness 解析自然语言来判断“这是不是一次调用”，也都不依赖模型自报 caller。真正的共同事实是：Adapter / Harness 必须先拥有角色到 server instance、capability 或 execution attempt 的可信映射，然后由 Harness 先校验再写入。通道不能替代平台账号鉴权、Agent 进程隔离、恶意同用户防护或未覆盖原生工具治理。

本轮没有自然出现 Agent 自述与服务端事实冲突；两端主路径摘要都与 request id 和最终事实一致。因此只确认对照方法成立，不声称 Agent 文本已经变得可信。若未来发生冲突，服务端事实仍是判定依据。

## 当前结论

`有条件可行`。

核心门槛已经满足：Codex CLI 与 Claude Code CLI 都存在无需真人中转、机器可解析的本地 MCP 公共能力调用路径；三个最小能力均被真实 Agent 调用，合法写入、未知目标、无权限和身份注入可以由 Harness 确定性处理；角色身份来自 Harness / Adapter 已知通道上下文，而不是 Agent 自报；Agent 事件、工具结果和服务端事实能够通过 request id 对照。结构化返回请求还证明了不开放同 turn 工具时的备用往返路径，CLI 与 loopback HTTP 则提供了直接协议候选。

结论之所以不是无条件`可行`，是因为当前证据依赖明确前提：角色身份必须由专属 server instance 或 execution attempt 等 Harness 已知上下文映射；本轮 CLI / HTTP 只证明公开固定人工 capability 的单角色映射与拒绝逻辑，若进入正式候选还必须另行证明高熵生成、保密、短期生命周期、轮换和撤销。Codex 与 Claude Code 需要不同的配置和失败解释；Claude 当前显式 MCP 与 safe-mode 不兼容；MCP 客户端元数据存在版本兼容要求；Codex read-only 不构成 workspace 外强读取隔离；CLI / HTTP 没有完成本轮 Agent E2E；四条路径都没有证明凭据防窃取、恶意同系统用户隔离、送达、幂等、安全重试、崩溃中不确定写入、生产并发或远程鉴权。

对后续的直接影响是：Stargazing 6 可以采用本地 STDIO MCP 作为两个真实 Agent 的主实验通道，并保留结构化返回请求作为备用对照；这只是下一项实验候选，不是正式架构决定。服务中断后的不确定结果、重试和持久化仍按计划留给 Stargazing 7，权限与隔离保证强度留给 Stargazing 8。

## 尚未回答的问题

- 正式产品怎样创建、轮换、撤销并隔离角色专属身份锚点；
- 多个并发请求、长连接、server 重启和 session 恢复时 request id 与执行尝试怎样保持一致；
- 请求已经写入但响应丢失时如何表达结果未知，何时可以安全重试；
- 真实消息与委托持久化、送达和幂等需要哪些协议；
- MCP 版本与两个 CLI 升级后，工具 schema、客户端元数据和失败事件是否变化；
- 远程 Agent 或跨机器 Harness 采用何种鉴权与传输边界。

## 资料来源

- [Stargazing 4：异构 Agent 的共同接入边界](004-heterogeneous-agent-common-boundary.md)
- [OpenAI 官方 Codex MCP 文档](https://learn.chatgpt.com/docs/extend/mcp)
- [OpenAI 官方 Codex 非交互模式文档](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Claude Code 官方 MCP 文档](https://code.claude.com/docs/en/mcp)
- [Claude Code 官方程序化运行文档](https://code.claude.com/docs/en/headless)
- [Probe 5.1–5.4 实验说明](../../experiments/stargazing-005/README.md)
