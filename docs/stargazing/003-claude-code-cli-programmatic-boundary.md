# Stargazing 3：Claude Code CLI 程序化协作边界

日期：2026-09-02

状态：已完成

当前结论：有条件可行

性质：Claude Code CLI 当前版本与当前用户配置组合的能力边界实验，不是正式接入设计、生产实现或模型质量评测

## 要回答的问题

在 Stargazing 1 的共同评估协议下，当前安装和配置的 Claude Code CLI 是否能够作为 thread 内 Agent 角色的底层主体，被 Harness 无需人工操作终端地可靠启动、持续交互并取得可用或明确受阻的结果。

本项需要同时区分 Claude Code 产品能力、当前 CLI 版本提供的参数，以及用户实际配置的模型、认证和环境所形成的运行表现。官方文档描述的 Anthropic 标准路径不能自动替代本机实证。

## 已知前提与边界

1. 本轮最小坐标沿用 Stargazing 1：macOS `26.5.2`、`arm64`、Claude Code CLI `2.1.252`；实验开始前重新确认；
2. 用户已完成 Claude Code 的安装、登录和必要配置；本项不读取账号、密钥、认证文件、套餐、额度、provider endpoint 或配置值；
3. 当前用户可能为 Claude Code 配置了非默认模型或服务端。除非 CLI 的公开运行结果直接提供必要标识，本项不主动探查；结论绑定当前 CLI 与当前用户配置组合，不外推所有 Claude Code 用户；
4. Agent 工作样例只使用隔离临时 workspace 与人工数据，不允许修改真实项目，不主动测试敏感文件、真实外部服务或模型服务调用之外的 Agent 工具网络访问；
5. 可以观察 CLI 公开返回的 session id、事件、result、usage、cost estimate、duration、诊断和退出事实，但不保存完整原始 transcript；cost 是客户端估算，不等同于最终账单；
6. 需要 resume 的实验会使 Claude Code 在自身状态目录保存 session transcript；提示词与人工标记会进入该存储。本项不读取、复制或删除认证材料与既有 session；
7. 本项只验证 Claude Code CLI，不开始异构共同边界设计或 Stargazing 4。

## 官方资料形成的待验证认识

截至 `2026-09-02`，Claude Code 官方资料说明：

- `claude -p` / `--print` 用于脚本和 CI 的非交互调用；
- `--output-format json` 返回 result、session id 和 metadata，`stream-json` 提供逐行事件；
- `--json-schema` 可以约束结构化结果形状；
- `--resume <session-id>` 与 `--continue` 可以继续 `-p` 产生的 session；
- `--input-format stream-json` 支持程序化流式输入；Agent SDK 把长驻 streaming input 作为推荐交互方式，但 CLI 的真实持续输入行为仍需本机验证；
- `--bare` 跳过 hooks、plugins、MCP、auto memory 和 CLAUDE.md 等自动发现，是脚本推荐模式；但它仍提供 Bash / Read / Edit 等内置工具，显式 `/skill-name` 仍可解析，因此还需要单独禁用工具与 slash commands；同时它跳过 OAuth / keychain，要求显式 API key、provider credentials 或传入 settings；
- `dontAsk` 会拒绝没有预先允许的工具，`allowedTools` / `disallowedTools` 可以表达工具规则；这些是权限决策边界，不自动等于 OS 级读写或网络隔离；
- JSON metadata 可以包含 usage、总成本与分模型成本，`--max-budget-usd` 和 `--max-turns` 提供调用限制入口。

这些是官方声明，不是本机可行性结论。特别是当前用户配置是否能在 bare 模式工作、权限参数能强制到什么范围、第三方模型是否返回完整 client-side cost estimate metadata，都必须实测。

## 当前假设

### 假设一：存在无人工终端操作的机器可读调用路径

当前配置下至少存在一种 `claude -p` 调用方式，能够取得明确 session id、Agent result、usage / cost estimate metadata、终止状态和进程退出事实，而不要求人工审批或终端交互。

### 假设二：明确 session id 可以维持角色连续性

首次调用返回的 session id 可以被 `--resume` 明确指定，并保留前一轮文本上下文；不同 session 不依赖 `--continue` 这类隐式最近选择，也不会在最小样例中串线。

### 假设三：bare 或等价受控入口可以减少环境注入

当前认证方式能够支持官方推荐的 bare 自动化模式，或者存在另一条经过明确审查、不会静默加载未知 hooks / MCP / plugins 的受控入口。若 bare 与当前配置不兼容，则这本身是 Harness 接入条件，而不是理由充分的自动降级。

### 假设四：结果、受阻、故障与未知可以分层

结构化 result 可以表达 completed / blocked 的 Agent 语义；无效 session、权限拒绝、预算或 turn 限制、API 错误和进程取消能留下足以区分 CLI 事实与 Agent 声明的证据。

### 假设五：最小角色隔离与并发可行，但权限保证有限

不同 session 与 workspace 可以支撑两个最小角色并发；工具 allow / deny 和 permission mode 能控制被 Claude Code 调用的工具范围，但不在缺少证据时宣称实现完整文件、网络或外部副作用隔离。

## 反证条件

出现以下任一事实时，应收缩或否定相应假设：

1. `-p` 仍需要人工选择、批准或操作 TUI；
2. stdout 无法稳定解析，或 session / result / usage /终止事实无法可靠取得；
3. 指定 session id 无法恢复同一上下文，或不同 session 发生上下文、文件或 transcript 串线；
4. bare 无法使用当前认证，而任何可用替代路径都必须加载不可审查的外部 hook、MCP 或 plugin；
5. 工具拒绝、Agent 正常 blocked、调用故障和进程取消在可观察事实中无法区分；
6. 取消后残留进程或 workspace 文件，或退出事实会伪装成确定成功；
7. 两个最小角色无法并发，或共享 session / workspace 状态发生污染；
8. cost / usage / max budget 在当前模型或 provider 下缺失、失真或仅能作为弱提示；
9. 某项 Stargazing 1 默认忽略的环境因素实际影响核心结论。

## 验证方法与计划证据

每个 Agent 探针使用新建的系统临时 workspace 和人工输入。记录脱敏命令形态、公开事件或 JSON 字段、session 事实、stdout / stderr、退出状态、预期与实际文件副作用；完整原始输出和本地 transcript 不提交仓库。

### Probe 3.0：当前命令表面与安全基线

- 重新确认最小坐标，读取 `claude --help`；
- 对照官方资料确认 `-p`、bare、resume、输出格式、schema、工具权限、session 持久化、budget / turns 等参数；
- 先确定无工具调用的最小安全参数，再运行 Agent；
- 若 bare 无法沿用当前认证，不自动切换普通模式，先记录并重新审查替代路径。

### 本机 help 后形成的候选安全基线

本机 `2.1.252` help 还提供了两项与当前用户配置兼容性相关的受控入口：

- `--safe-mode`：禁用 CLAUDE.md、skills、plugins、hooks、MCP、custom commands / agents 等自定义内容，但保留 auth、model、built-in tools 与 permissions；
- `--restricted`：移除 Bash、PowerShell、REPL 等代码执行工具和 WebFetch（除非显式重新加入），忽略 user / project / local settings，将文件工具限制在工作目录与显式 add-dir 范围，并拒绝 bypass permissions。

因此运行前候选顺序是：

1. 先用 `--bare`、`--disable-slash-commands`、`--tools ""`、`--no-chrome`、`--strict-mcp-config` 和 stream-json 输出做无工具认证门槛，并从 `system/init` 实际检查 tools、plugins 与 MCP，而不是只相信参数名称；
2. 若 bare 只因它明确跳过的 OAuth / keychain 认证失败，替代基线限定为 `--safe-mode --restricted --disable-slash-commands --strict-mcp-config --tools "" --no-chrome --permission-mode dontAsk`，因为本机 help 明确说明它在禁用自定义内容的同时保留 auth / model；同样以 `system/init` 和实际行为验证；
3. 不使用 `--dangerously-skip-permissions`、`--allow-dangerously-skip-permissions`、`bypassPermissions`、`--add-dir`、Chrome、cloud、remote control、background agent 或外部 plugin；
4. 只有 Probe 3.4 的特定临时文件子项才显式开放最小文件工具；只有取消探针才显式开放精确的等待命令；
5. `--no-session-persistence` 只用于不需要 resume 的辅助探针，不能用于连续性验证。

本项默认不传 `--settings`。本机 help 明确说明 print 模式会静默忽略校验失败的 settings；若后续确实必须用 settings 才能建立认证或受控环境，应先暂停并补写验证方法，通过 `system/init` 或行为证据确认关键配置生效，不能把退出码 `0` 当作配置生效证明。

候选基线仍需运行前审查和真实实验确认。help 声称 restricted 会限制文件工具范围，不等于本项已经证明 OS 级隔离。

### Probe 3.1：bare 非交互启动与机器可读结果

- 优先使用 bare、无工具或显式拒绝工具、无 Chrome、JSON / stream-json 输出；
- 要求只返回人工标记，不读取文件、不进行模型服务调用之外的 Agent 工具网络访问；
- 检查 system init 中的 tools、plugins、MCP 与 model，并检查 session id、result、usage / cost estimate、duration、stderr 与退出码；
- 若 bare 在进入模型前因认证失败，将其记录为确定性条件，不读取凭证排障。

### Probe 3.2：明确 resume 与持续输入候选

- 用明确 session id resume 一个不需要工具的文本标记；每次 resume 都重新传入首次已经验证并选定的完整基线，包括所选的 `--bare`，或 `--safe-mode --restricted`，以及工具、slash command、MCP、Chrome 与 permission 参数，不假定首次调用的安全配置自动继承；
- 比较首次调用与 resume 的 `system/init`，若工具、plugin、MCP 或权限环境漂移则停止；
- 新 session 检查最小上下文隔离；
- 在当前 help 和官方协议足够明确时，增加一次 `--input-format stream-json` 的受控多消息实验，判断长驻进程是否比逐次 resume 更适合 Harness；该探针必须使用独立进程组与硬超时，只发送有限消息，完成后主动关闭 stdin，并在超时或协议未终止时停止进程组、检查残留进程与 workspace；
- 不把 session transcript 持久化误写成 workspace 内行为。

### Probe 3.3：结构化完成与受阻

- 使用预定 schema：`work_status`（`completed` / `blocked`）、`result`、`reason`；
- 分别运行可完成与缺少必要人工输入的样例；
- 明确 result subtype、进程成功只表示调用完成，work status 是 Agent 声明而非客观验收。

### Probe 3.4：工具权限与临时 workspace

- 在 bare 或已审查的受控模式中，只为单项探针显式开放必要工具；
- 验证允许创建一个人工文件、明确拒绝写入时文件不存在；
- 对工具 allow / deny、permission mode 和实际磁盘结果分层记录；
- 不主动测试 workspace 外读取。若 Agent 意外访问外部文件，立即暂停并重新评估；
- 不把 Claude Code 权限规则外推为 OS、容器或强制断网保证。

### Probe 3.5：故障、预算限制与进程取消

- 无效 session id 应在 Agent turn 前明确失败；
- 只在无额外成本或极低上限的安全条件下验证 max turns / budget 的可观察结果，不为凑结论消耗或购买额度；
- 对只涉及临时目录的等待命令建立独立进程组，观察工具开始后有界终止，检查事件、退出、残留进程与文件；
- 取消探针只允许精确等待命令，不开放通配 Bash；使用明确 PID / 进程组，不按进程名称广泛终止；为启动、等待、终止和残留检查设置硬超时；
- 没有明确成功/失败终态时归类为结果未知。

### Probe 3.6：两个独立角色的最小并发

- 在两个临时 workspace 近同时启动两个短任务；
- 使用不同人工标记与 session id；
- 检查进程是否真实重叠、结果与文件是否交叉；
- 不做压力测试，不推导生产容量或账户限流。

## 预定判断标准

核心门槛成立至少需要：

1. 无需人工终端操作即可启动；
2. 机器可解析结果中存在明确 session id、最终结果和终止 / error 事实；
3. 指定 session id 可以接受后续输入并保留语义连续性；
4. 不同 session 与 workspace 能建立最低限度角色隔离；
5. 成功、Agent blocked、至少一种调用故障和进程取消具有可观察差异；
6. 环境加载、工具权限、usage / cost estimate 和 budget 的真实强弱边界被公开；
7. 所有未验证的文件、网络、外部副作用和容量范围不被描述为已保证。

若核心路径成立但必须依赖当前用户配置、特定输出适配或存在未覆盖限制，本项结论为`有条件可行`。一次 `-p` 成功不自动满足核心门槛。

## 当前观察

已经重新确认最小坐标为 macOS `26.5.2`、`arm64`、Claude Code CLI `2.1.252`。本机 `claude --help` 成功退出，确认当前版本实际提供：

- `-p`、`--output-format json / stream-json`、`--input-format stream-json` 与 `--json-schema`；
- `--resume`、`--continue`、`--session-id`、`--fork-session` 与 `--no-session-persistence`；
- `--bare`、`--safe-mode`、`--restricted`、`--setting-sources` 与 `--strict-mcp-config`；
- `--tools`（空字符串可禁用全部 built-in tools）、allowed / disallowed tools 与 permission mode；
- `--max-budget-usd`、`--max-turns`、`--no-chrome`；
- permission bypass 被 help 明确标为危险；add-dir、cloud、remote control、background 等虽非同类危险警告，本项因超出探针范围也默认不用。

### Probe 3.1A：bare 非交互启动

在新建临时 Git workspace 中使用 `--bare --disable-slash-commands --tools "" --no-chrome --strict-mcp-config --permission-mode dontAsk` 与 stream-json 输出，执行一个只返回人工标记的无工具任务。

本轮无需人工终端操作，约 3 秒完成并以退出码 `0` 结束。`system/init` 与最终 result 提供了以下可解析事实：

- 明确且一致的 session id；
- `tools=[]`、`mcp_servers=[]`、`slash_commands=[]`、`skills=[]`；
- permission mode 为 `dontAsk`；
- 实际模型为用户当前配置的 `deepseek-v4-flash` 变体；
- result 与人工标记完全一致，`subtype=success`、`is_error=false`、`terminal_reason=completed`；
- usage、duration、turn 数和 `total_cost_usd` client-side estimate；model usage 同时说明 cost basis unknown，因此不把该值视为账单；
- web search / fetch 计数均为零，没有工具或 subagent 执行。

CLI 还向诊断流报告当前模型不被它的 session title 与 SDK 模型识别表识别，但没有阻止本轮完成。这是当前用户自定义模型配置影响输出解析的直接证据。

重要反例是：`system/init` 的 `plugins` 仍列出 10 个本地 plugin 元数据及 workspace 外绝对路径。当前 tools、skills 与 MCP 均为空，没有观察到 plugin 工具执行，但 bare 不能被描述为“输出和上下文中完全没有本地 plugin 环境痕迹”。完整 plugin 名称与路径不写入项目记录。

因此在选定后续基线前，增加一个同等无工具的 `--safe-mode --restricted` 对照。若其 init 更干净且当前认证仍可用，后续优先使用该组合；否则把 bare plugin metadata 暴露作为明确接入条件。

### Probe 3.1B：safe-mode + restricted 对照

在另一个新建临时 Git workspace 中，使用 `--safe-mode --restricted --disable-slash-commands --strict-mcp-config --tools "" --no-chrome --permission-mode dontAsk` 执行同等的无工具人工标记任务。

本轮同样无需人工终端操作，约 3 秒完成并以退出码 `0` 结束。`system/init` 和最终 result 表明：

- `tools=[]`、`mcp_servers=[]`、`slash_commands=[]`、`skills=[]`、`plugins=[]`；
- permission mode 为 `dontAsk`，实际模型仍是当前配置的 `deepseek-v4-flash` 变体；
- session id 在 init、assistant 与 result 事件中一致；
- result 与人工标记完全一致，`subtype=success`、`is_error=false`、`terminal_reason=completed`；
- usage、duration、turn 数与 client-side cost estimate 字段仍然可解析，cost basis 仍为 unknown；
- 没有工具或 subagent 执行，web search / fetch 计数均为零。

与 bare 对照相比，本轮 `plugins=[]`，没有再次暴露本地 plugin 名称与路径元数据；当前认证和自定义模型也仍可使用。诊断流仍报告当前模型不在 Claude Code 的部分模型识别表中，因此这是模型适配诊断，与 bare / safe-mode 选择无关。

后续探针据此选用 `safe-mode + restricted` 组合作为当前版本、当前用户配置下的最小受控基线，并在每次新调用和 resume 时完整重传其余禁用参数。这个选择只证明 Claude Code init 所报告的自定义内容与工具表面更干净，不证明 OS 级文件隔离、进程隔离或网络隔离，也不能外推到其他版本和用户配置。

### Probe 3.2A：显式 resume

使用 Probe 3.1B 返回的明确 session id，在原临时 workspace 中调用 `--resume`，同时重新传入完整的 `safe-mode + restricted` 无工具基线，而不依赖 session 继承安全参数。

恢复调用约 4 秒内完成、退出码为 `0`，并返回了上一轮的精确人工标记。恢复前后的 init 对比显示：

- session id 保持一致；
- `tools`、`mcp_servers`、`slash_commands`、`skills` 与 `plugins` 继续为空；
- permission mode、模型和 Agent 列表没有漂移；
- result 为 success / completed，且没有工具、网络工具或 subagent 执行。

这证明当前版本与配置组合可以用显式 session id 保持最小文本上下文连续性，同时允许 Harness 在每次恢复时重新声明并核验受控运行表面。项目记录不保存实际 session UUID。

### Probe 3.2B：新 session 最小隔离

在新的临时 workspace 中，不传 resume 或 continue，启动同一安全基线并要求它只根据本轮对话判断是否存在更早用户输入。该调用返回新的 session id，并明确返回“没有更早 turn”的人工标记；init 仍保持全部自定义表面与工具为空。

这是一条支持新 session 不继承另一 session 文本上下文的最小语义证据，但不是对 Claude Code 内部 transcript 存储、账号侧数据或所有隐式环境的形式化隔离证明。后续 Harness 仍应显式管理 session id，不能用 `--continue` 代替角色映射。

### Probe 3.2C：streaming input 候选

依据官方 `SDKUserMessage` 形状，使用 `--input-format stream-json --output-format stream-json --replay-user-messages` 启动受控长驻进程，并以独立进程组、有限消息、结果超时、stdin 主动关闭和有界清理驱动双消息实验。

首次实验出现了两个连续、可复现的认证失败：

1. 未显式传模型时，streaming-input init 回落到默认 Claude 模型，而不是一次性 `-p` 已观察到的用户模型，随后返回 `authentication_failed`；
2. 显式传入同一个 `deepseek-v4-flash` 模型后，init 的模型字段正确，但仍在模型调用前返回相同的 `authentication_failed`。消息协议本身已被接受并 replay，进程正常退出，没有超时或残留清理失败。

后续取消探针发现，这两次调用都从系统临时目录作为宿主 workdir 启动，没有保留先前成功调用对应的完整启动上下文。因此认证失败不能归因于 streaming input 或 provider 不兼容，只能先视为启动上下文反例；具体影响来自环境变量、配置解析位置还是其他宿主条件，本项没有继续读取配置归因。

控制变量复验从已验证可用的启动上下文启动驱动器，只把 Claude 进程 cwd 指向新的临时 workspace。完全相同的双消息 streaming 协议随后成功：

- 两条 user message 均被 replay，并各自产生一个 success / completed result；
- 第二条结果正确引用第一条人工标记，证明同一长驻进程中的文本上下文连续；
- 全部事件只有一个 session id；
- init 的模型恢复为当前 `deepseek-v4-flash` 变体，tools、MCP、slash commands、skills 与 plugins 仍为空；
- 主动关闭 stdin 后进程正常退出 `0`，没有触发超时或进程组清理。

因此，当前 CLI 与用户配置组合下，`--input-format stream-json` 持续输入路径`有条件可行`，显式 session id + 逐次 resume 也已独立跑通。二者都要求保留或明确构造已经验证可用的启动上下文；未来接入可以按交互、恢复与部署需要选择，但不能在失败时静默切换或假定配置天然一致。

### Probe 3.3：结构化完成与受阻

使用同一 JSON Schema 分别执行一个可直接完成的计算任务和一个缺少收件人与消息内容、且没有工具可用的发送任务。schema 要求 `work_status` 只能为 `completed` 或 `blocked`，并必须返回字符串形式的 `result` 与 `reason`。

两次调用均无需人工交互、退出码为 `0`，result 均为 success / completed，并提供独立的 `structured_output`：

- 可完成样例返回 `work_status=completed` 与预期结果；
- 缺少必要输入的样例返回 `work_status=blocked`、空结果与明确缺失信息；
- 两次均没有 permission denial、subagent 或网络工具使用；
- JSON result 自身可解析，`structured_output` 省去 Harness 从自由文本中提取状态的需要。

这里必须分两层理解：CLI 的 `subtype=success`、`terminal_reason=completed` 与退出码 `0` 只说明本次 Agent 调用和 schema 输出完成；`work_status` 是 Agent 对工作的语义声明，不是 Harness 的程序化验收结果。当前版本还把结构化输出过程的底层 `stop_reason` 报为 `tool_use`、turn 数为 2，因此 Harness 不能把底层 stop reason 直接映射为“Agent 调用了已开放的业务工具”。

### Probe 3.4：工具可用性、权限拒绝与磁盘事实

在三个独立临时 workspace 中分别验证：明确开放并批准 `Write`、完全不提供工具、提供 `Write` 但以 `dontAsk` 拒绝未预先批准的调用。

实际结果分为三层：

1. `tools=[Write]` 且 permission mode 为 `acceptEdits` 时，Agent 创建了预期文件；独立磁盘检查确认文件为 26 字节，内容与结尾换行完全匹配；
2. `tools=[]` 时，目标文件不存在，证明禁用工具阻止了本次文件副作用；但当前模型在文本中伪造 shell 代码块和工具调用标记，并错误声称命令成功，最终 CLI 仍以 success / completed 结束；
3. `tools=[Write]` 且 permission mode 为 `dontAsk` 时，真实 `Write` tool use 被 Claude Code 拒绝，stream 中出现 `system/permission_denied` 与错误 tool result，最终 result 的 `permission_denials` 列表包含该调用，独立磁盘检查确认文件不存在。CLI 进程仍以退出码 `0` 和 success / completed 结束，Agent 在后续文本中正确说明受阻。

据此，`system/init` 的工具表、permission-denied 事件、result 的 denial 元数据和实际外部状态可以成为 Harness 的确定性证据；Agent 文本里的代码块、工具样式标签和成功措辞都不能替代这些证据。`dontAsk` 是拒绝需询问工具的可观察强制边界，但 `tools=[]` 不会自动生成 denial，因为工具根本没有暴露给 Agent。

restricted 对文件工具工作目录的限制本项没有主动做 workspace 外读取试验，因此仍只作为当前官方声明与待独立验证边界，不能写成已经证明的 OS 级保证。

### Probe 3.5A：无效 session、turn 上限与预算上限

三项受控反例给出了不同故障形状：

- 恢复不存在但格式合法的 session id 时，CLI 在 Agent turn 前以退出码 `1` 失败并明确报告找不到 conversation，没有生成 Agent result；
- `--max-turns 1` 样例在第一次 Agent 响应发出 Write 调用并被权限拒绝后，不再允许第二次 Agent 响应，返回退出码 `1`、`subtype=error_max_turns`、`terminal_reason=max_turns`、`is_error=true`，磁盘文件不存在；
- `--max-budget-usd 0.000001` 样例返回退出码 `1`、`subtype=error_max_budget_usd`、`terminal_reason=budget_exhausted`、`is_error=true`，但已经发生一次模型调用，client-side model usage estimate 为约 `$0.0077`，明显超过配置阈值后才停止。

因此，无效 session、turn limit 与 budget limit 都有可机器区分的失败证据，但当前 `max-budget-usd` 不能被描述为“首次模型调用前绝不超过的硬成本上限”。它在本探针中是跨后续调用 / turn 的停止门槛，且所依据的成本本身仍是当前 provider 下 cost basis unknown 的客户端估算。Harness 若向用户提供资源预算强保证，需要另有调用前计量、保留额度或 provider 侧限制，不能直接把这个 CLI 参数包装成严格预算保证。

### Probe 3.5B：进程级在途取消

取消探针先发现两项实验边界：

- 从最小系统临时目录作为宿主 workdir 直接启动驱动器时，Claude Code 回落默认模型并认证失败；从已经验证可用的项目启动上下文运行同一驱动器、再把 Claude 进程 cwd 指向临时 workspace 后恢复为已验证的用户模型和认证路径。证据只证明启动上下文影响当前模型 / 认证解析，没有唯一定位到环境变量、配置目录或其他来源。正式 Harness 因而必须保留或明确构造已经验证可用的启动上下文，不能只假定可执行文件绝对路径足够；
- restricted 模式即使显式加入精确 Bash 规则，也会额外阻止独立等待命令，无法构造真实在途等待。移除 restricted 后仍保留 safe-mode、唯一 Bash 工具、唯一预批准等待命令、`dontAsk` 与临时 workspace，作为只验证取消的受控例外。

最终探针观察到精确 Bash tool-use 后，在尚未收到 tool-result、Claude 进程仍在运行时向独立进程组发送 `SIGTERM`。结果为：

- Claude CLI 退出码为 `143`；
- 没有最终 result 事件，因此没有伪装成 success；
- 没有 permission-denied 或 tool-result 事件先于取消；
- 取消后没有发现精确等待命令残留进程。

这证明 Harness 可以用自己持有的进程组把当前 CLI 调用停止，并将“已发起外部取消但没有 Agent 终态”作为独立运行事实；它不证明 Claude Code 会为外部 SIGTERM 生成结构化 cancelled result，也不证明所有工具执行器、远程副作用或已发生费用都可撤销。由于 underlying wait runner 不作为可见子进程稳定暴露，本项只确认 CLI 边界上的在途 tool-use 与取消后无本机精确等待残留，不声称底层执行器的普遍取消保证。

### Probe 3.6：两个独立角色的最小并发

在两个独立临时 workspace 中近同时启动两个无工具、无 session 持久化的短任务，并分别使用不同人工标记。两次调用的实际时间区间重叠约 3 秒，而不是串行执行；二者均退出 `0`，返回不同 session id、各自唯一且完全匹配的标记、success / completed 终态，没有 permission denial、网络工具或 subagent 使用。

这证明当前 CLI、模型与用户配置组合能够支撑两个最小独立调用并发，且本样例没有结果串线。它不证明同一 session 可并发写入，不证明同一 workspace 的并发安全，也不形成生产并发数、provider 限流或成本容量结论。Harness 仍应保持“一角色一 session”，并由更高层明确控制 workspace 冲突与账户并发。

## 结论矩阵

| 评估维度 | 观察结论 | Harness 可依赖程度 |
| --- | --- | --- |
| 非交互启动 | `claude -p` 无需人工终端操作即可完成 | 可依赖，但绑定安装、登录、provider 与已验证启动上下文前提 |
| 机器可读输出 | JSON / stream-json 提供 init、assistant、result、usage、诊断与 session id | 可依赖结构形态；不能只看退出码、subtype 或单个 stop reason |
| session 连续性 | 明确 session id 可 resume，并保留文本上下文 | 可作为同一逻辑角色的当前连续性基础；每次需重传并核验运行基线 |
| 新 session 隔离 | 新 session 使用不同 id，最小样例未见文本串线 | 初步可用，不构成内部存储或账号侧绝对隔离证明 |
| CLI streaming input | 已验证启动上下文下双消息、同 session、上下文连续并正常关闭 | 有条件可用；启动上下文变化时可能在 Agent turn 前认证失败 |
| 结构化工作状态 | JSON Schema 可得到 completed / blocked 与原因 | 是 Agent 语义声明，不是客观验收或 CLI 工作状态认证 |
| 工具可用性 | init 明确列出工具；只开放 Write 时可产生真实文件 | 工具表与实际事件可作为调用边界证据 |
| 工具禁用 | `tools=[]` 时没有文件副作用 | 可阻止本轮内置工具调用，但 Agent 文本可能伪造工具过程与成功 |
| 权限拒绝 | `dontAsk` 对未预批准 Write 产生 denial 事件和 result 元数据 | 当前可机器识别，并实际阻止该文件写入 |
| 环境自定义 | safe-mode + restricted 的 tools、MCP、skills、slash、plugins 均为空 | 当前实测最干净基线；不是 OS、网络或所有 managed policy 的隔离证明 |
| 启动上下文 | 更换宿主 workdir / 启动上下文后回落默认模型并认证失败 | 必须由接入层保留或明确构造已验证上下文；绝对可执行路径不足以保证可用，具体影响来源仍未决 |
| 调用前故障 | 无效 session 在 Agent turn 前非零退出且无 result | 可确定性识别本轮故障 |
| turn 上限 | 达限返回 error_max_turns / max_turns 和非零退出 | 可观察停止，但不能把 turn 数直接等同业务工作量 |
| budget 上限 | 极低阈值在首次模型调用已产生更高估算后才报 budget exhausted | 不能作为首次调用前硬成本上限；当前 cost basis 也为 unknown |
| 进程级取消 | 独立进程组可被 SIGTERM，退出 143、无 final result、无精确等待残留 | Harness 可记录外部取消事实；结果未知，不能保证撤销成本或副作用 |
| 最小并发 | 两个独立进程、workspace 与 session 真实重叠并正确完成 | 最小可行，不代表同 session / workspace 安全或生产容量 |

## 成立条件与未覆盖范围

将当前 Claude Code CLI 用作 Harness 中 Agent 角色的底层主体，至少需要接受并处理以下条件：

1. 当前连续交互有两条已验证候选：长驻 streaming input 与“明确 session id + 逐次 resume”。无论选择哪条，Harness 都必须保存角色与 session 的明确映射，并分别处理进程存活与恢复语义；
2. 每次调用与 resume 都应完整传入并核验选定的运行基线，不能假设安全参数、模型或环境从旧 session 自动继承；
3. 接入进程必须保留或明确构造用户已经配置和登录 Claude Code 时验证可用的启动上下文，可能涉及环境、配置解析位置或其他宿主条件；上下文不满足时应作为调用故障暴露，不能静默回落默认模型或普通模式；
4. Harness 必须联合解析 init、assistant/tool 事件、permission denial、result、stderr 与进程退出事实。Agent 文本、CLI success 或退出码 `0` 都不能单独证明工作成功；
5. `safe-mode + restricted` 适合作为当前受控起点，真实角色需要工具时再按角色能力最小开放。没有验证的 OS 文件、进程、网络和远程副作用隔离不能因参数名称被视为强保证；
6. JSON Schema 可以固定 Agent 声明形状，但不能替代委托发布者理解、评审、验收或其他语义治理；
7. 外部进程取消没有结构化 Agent 终态，应按 Harness 自己记录的取消事实与结果未知处理；不自动重试，不假设成本和副作用已经撤销；
8. `max-budget-usd` 在当前 provider 下不是首次调用前的严格硬上限。产品若提供资源预算强保证，需要另行建立确定性覆盖范围；
9. 当前自定义模型能运行，但 Claude Code 会报告部分 `unrecognized_model` 诊断；适配层需要容忍已知非致命诊断，同时避免把所有 stderr 都降级为无害。

本项没有验证：workspace 外真实读取范围、强制断网、managed policy 的全部影响、完整 MCP / hook / plugin 隔离、不同工具的权限矩阵、session transcript 跨进程迁移、认证续期、provider 限流、账户总预算、长期并发、同 workspace 并发写入、跨 Harness 重启恢复、远程副作用幂等与生产安全。它们不能因核心路径跑通而被视为可行。

## 当前结论

`有条件可行`。

Probe 3.1–3.6 已满足 Stargazing 3 的核心门槛：当前坐标与用户配置组合下，Claude Code CLI 可以无需人工终端操作启动，返回机器可解析的 session、结果、用量估算和终止事实；明确 session id 可以 resume 并保留文本上下文；结构化 completed / blocked 声明、工具允许与权限拒绝、部分调用故障、进程级取消和两个独立角色最小并发都具有可观察证据。

它不是无条件可行：streaming input 与逐次 resume 都要求使用已经验证可用的启动上下文，上下文变化可能回落默认模型并认证失败，具体影响来源仍未决；Agent 文本可能伪造未发生的工具成功；外部 SIGTERM 没有结构化取消终态；极低 `max-budget-usd` 会在一次模型调用已经超过阈值后才停止；safe-mode / restricted 与工具权限也没有被证明等同完整 OS 或网络隔离。

因此当前建议是把 Claude Code CLI 保留为 Harness 的可行候选接入对象，并把“streaming 与 resume 双路径、启动上下文前提、完整基线声明、多源事实解析、权限事件优先、取消后结果未知、预算覆盖透明”作为后续共同边界研究必须保留的事实。正式接入设计仍待 Stargazing 4，不在本项决定。

本项结论只适用于记录日期、Claude Code CLI `2.1.252`、macOS `26.5.2` / `arm64` 与当前用户 provider / 模型 / 登录配置组合；版本或关键运行条件变化后，应按 Stargazing 1 原则局部复验。Stargazing 3 完成不会自动开始 Stargazing 4。

## 资料来源

- [Claude Code 官方程序化运行文档](https://code.claude.com/docs/en/headless)
- [Claude Code 官方 CLI 参考](https://code.claude.com/docs/en/cli-usage)
- [Claude Code 官方 session 文档](https://code.claude.com/docs/en/sessions)
- [Claude Agent SDK 官方 streaming input 文档](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode)
