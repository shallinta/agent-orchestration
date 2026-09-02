# Stargazing 2：Codex CLI 程序化协作边界

日期：2026-09-02

状态：已完成

当前结论：有条件可行

性质：Codex CLI 当前版本的能力边界实验，不是正式接入设计、生产实现或技术选型

## 要回答的问题

在 Stargazing 1 的最小兼容性坐标与共同评估协议下，Codex CLI 是否能够作为一个 thread 内 Agent 角色的底层主体，被 Harness 无需人工操作终端地可靠启动、持续交互并取得可用或明确受阻的结果。

本项重点不是判断 Codex 完成业务任务的质量，而是验证程序化边界是否提供了足够事实，使未来 Harness 能区分：正常完成、正常受阻、调用故障与结果未知。

## 已知前提与边界

1. 本轮最小坐标沿用 Stargazing 1：macOS `26.5.2`、`arm64`、Codex CLI `0.144.6`；实验开始前重新确认这些坐标；
2. 用户已经完成 Codex CLI 的安装、登录和必要配置；本项不读取账号、凭证、认证文件、套餐或额度；
3. 只使用隔离临时目录中的人工样例，不允许 Codex 修改本项目或其他真实项目；
4. 不执行 push、PR、发布、部署、通知、购买或面向真实外部系统的操作；
5. 可以观察 Codex CLI 自身公开返回的事件、session id、usage、诊断和退出事实，但不读取内部认证材料；
6. 本项只验证 Codex CLI，不开始 Claude Code CLI 实验，不决定未来共同接口。

## 官方资料形成的待验证认识

截至 `2026-09-02`，OpenAI 官方非交互模式文档与本机 `--help` 说明：

- `codex exec` 用于脚本和 CI 中的非交互运行；
- 普通模式把进展写到 stderr，并把最终 Agent 消息写到 stdout；
- `--json` 把 stdout 转换为 JSONL 事件流，事件可能包括 thread、turn、item、error 和 usage；
- `codex exec resume <SESSION_ID>` 或 `--last` 可以继续非交互 session；
- Codex 默认要求位于 Git 仓库内，也提供跳过检查的显式选项；
- 可以显式设置 sandbox，并可以请求 schema 约束的最终输出；当前本机 help 没有普通 approval 参数，只有明确标为危险的 bypass 参数，本项不使用后者。

这些是官方资料声称的能力，不是本项实验结论。

## 当前假设

### 假设一：存在稳定的非交互启动与结果边界

Harness 可以启动 `codex exec`，通过 JSONL 事件取得 thread id、执行进度、最终 Agent 消息、usage 和终止事实；成功执行能够由结构化事件与进程退出共同确认。

### 假设二：session id 足以关联同一逻辑角色的后续输入

首次执行返回的 thread id 可以作为后续 `resume` 的明确目标；指定 id 的恢复不会依赖“最近一次 session”这种进程外隐式选择，并能保留前一轮语义上下文。

### 假设三：多个逻辑角色可以保持最低限度隔离

为不同角色使用不同 thread id 与不同工作目录时，角色上下文和文件副作用不会互相串联；独立进程可以同时运行。

### 假设四：关键异常至少可以被诚实分类

无效参数、无效 session、Git 仓库前提不满足、Agent 正常受阻及进程被取消，会留下足够的事件、诊断或退出事实，允许 Harness 区分已知失败与无法确认结果的情形。

### 假设五：权限与资源只存在有限可观察和可强制范围

显式 sandbox 可以对本地文件行为形成可观察约束，JSONL usage 可以提供部分 token 统计；但取消外部副作用、网络、Agent 原生能力和账户总预算不应在没有证据时宣称已受 Harness 强制控制。

## 反证条件

出现以下任一事实时，应收缩或否定相应假设：

1. 非交互执行仍需要人工终端输入，或 stdout 无法稳定机器解析；
2. 成功、失败或正常受阻缺少可用的事件与退出事实，导致 Harness 必须猜测自然语言；
3. 无法取得明确 session id，或指定 id resume 不能维持同一逻辑上下文；
4. 不同 session 或工作目录发生不可接受的上下文、文件或进程污染；
5. 取消后仍有无法发现的子进程或新增副作用，而 CLI 又把结果表达为确定失败；
6. sandbox 的实际行为与公开配置不一致，或只能依赖提示词遵守；
7. usage、耗时或成本信息不足以支撑任何强预算保证；
8. 某项 Stargazing 1 默认忽略的环境因素实际影响核心结论。

## 验证方法与计划证据

所有 Agent 工作探针的工作目录和人工样例都在新建的系统临时目录中。需要 resume 的探针有一项必要例外：Codex CLI 会把自身 session / rollout 写入用户 Codex 状态目录，以便后续按 session id 恢复；人工标记和提示词会进入该会话存储。本项不读取、复制或删除认证材料与既有 session，也不把本轮原始会话记录提交 Git。`--ephemeral` 只可用于不需要恢复的辅助探针，不能用于 Probe 2.2 的连续性基线。

每个探针记录脱敏命令形态、工作目录性质、输入、相关 JSONL 事件类型、stdout / stderr 分层、退出状态、预期文件副作用和实际副作用；原始完整输出不提交仓库。

### 默认隔离调用基线

除非单项探针明确说明差异，Probe 2.1–2.6 的首次 `exec` 调用都使用当前 help 已确认支持的：

- `--ignore-user-config`：不加载用户 `config.toml`，但仍复用用户已经准备好的认证；
- `--ignore-rules`：不加载用户或项目 execpolicy `.rules`；
- `--sandbox read-only`：首次 `exec` 默认禁止 Agent 写入 workspace；Probe 2.4 的受控写入子项才切换为 `workspace-write`；
- `--color never`：避免 ANSI 颜色污染诊断记录；resume 当前 help 未提供该参数，因此只在首次 `exec` 使用；
- 提示词明确要求不使用网络、MCP 或其他外部服务，只处理人工样例。该提示词要求属于弱约束；真正的本地文件写入限制来自 sandbox，本项不声称已强制断网。

`codex exec resume --help` 没有直接提供 `--sandbox` 或 `--color`。恢复后的有效 sandbox 是否继承、能否通过已确认配置指定，都是 Probe 2.0 / 2.2 的待验证事实；验证前不宣称 resume 受到首次 `exec` 的强制只读保证，也不猜测配置 key。Probe 2.2 因此只处理不需要工具的文本标记，并在提示词中要求不调用工具、不写文件和不访问外部服务；这些恢复轮要求属于弱约束。

所有探针禁止使用 `danger-full-access`、`--dangerously-bypass-approvals-and-sandbox`、`--dangerously-bypass-hook-trust` 和 `--add-dir`。本项不会主动配置或调用 MCP、hook、plugin、Skill 或外部服务。

### Probe 2.0：当前命令表面

- 读取 `codex exec --help` 与 `codex exec resume --help`；
- 对照官方资料，确定当前版本实际支持的参数；
- 不读取用户配置或认证信息。

### Probe 2.1：非交互启动与机器可读结果

- 在隔离 Git 仓库中运行一次只读、无工具需求的最小任务；
- 使用 JSONL 输出，检查 thread、turn、Agent 消息、usage 和退出事实；
- 检查 stdout 是否逐行可解析，stderr 是否与协议输出分离。

### Probe 2.2：指定 session 的连续输入

- 首轮让 Agent 记住一个随机人工标记但不写文件；
- 从结构化事件取得 thread id；
- 用该 id resume，要求返回先前标记；
- 另启 session，确认不会自然获得该标记。

### Probe 2.3：结构化最终结果

- 使用预先固定的最小 JSON Schema，请求 `work_status`（`completed` 或 `blocked`）、`result` 和 `reason`；
- 检查最终输出与 schema、JSONL 事件和退出事实之间的关系；
- `exit 0` 与 `turn.completed` 只证明 CLI turn 完成；`work_status` 是 Agent 按契约生成的语义声明，不是 CLI 对工作事实的客观认证；
- 不把 schema 成功等同于任意业务结果可信。

### Probe 2.4：工作目录与 sandbox

- 在隔离目录分别验证只读任务、允许在 workspace 写一个人工文件、read-only 下请求写文件；
- 比较实际文件系统副作用与 Agent 返回；
- 不测试真实仓库、外部目录或敏感路径越界；所得 sandbox 结论只覆盖本轮临时 workspace 的文件写入，不外推网络、外部目录或 Agent 其他原生能力。

### Probe 2.5：失败、受阻与结果未知

- 使用无效 session id 验证恢复失败；
- 在非 Git 临时目录验证默认仓库前提；
- 使用 Probe 2.3 预定义 schema，让 Agent 对缺失且禁止猜测的人工输入返回 `work_status=blocked`；这只验证机器可解析的 Agent 语义声明，不把它伪装成 CLI 客观故障；
- 无效 resume、`turn.failed`、`error` 或非零退出作为调用边界事实单独记录；
- 启动可安全中断的长等待探针并从父进程请求取消；为探针设置有界等待时间，终止独立进程组，再检查残留进程与文件；取消后如果没有可确认终态，分类为`结果未知`，不擅自归为成功或失败；
- 无法安全确定的结果明确记为未知，不为凑结论扩大实验风险。

### Probe 2.6：独立角色并发与隔离

- 在两个隔离工作目录启动两个短任务；
- 分别使用不同人工标记并取得不同 thread id；
- 检查事件、结果和文件是否交叉；
- 只验证最小并发可行性，不进行压力测试或推导生产容量。

## 预定判断标准

核心门槛成立至少需要：

1. 无需人工操作终端即可启动；
2. 能从机器可解析输出取得明确 thread id 与最终结果；
3. 能向指定 session 发送后续输入并保留语义连续性；
4. 能以不同 session 和工作目录建立最低限度角色隔离；
5. 至少成功、无效恢复和进程异常具有可观察差异；
6. 所有不能保证的权限、取消、预算和外部副作用范围均如实标记。

若核心门槛成立但存在适配限制，本项结论为`有条件可行`；只有当前证据足以支持且没有实质接入条件时才为`可行`。一次运行成功不自动满足核心门槛。

## 当前观察

已经重新确认最小坐标为 macOS `26.5.2`、`arm64`、Codex CLI `0.144.6`。本机 `codex exec --help` 与 `codex exec resume --help` 均成功退出，确认当前版本实际提供：

- 非交互初始 prompt、从 stdin 读取输入；
- `resume` 指定 UUID / thread name 或选择最近 session；
- `--json`、`--output-schema`、`--output-last-message`；
- `--sandbox`、`--cd`、`--skip-git-repo-check`、`--ephemeral`；
- `--ignore-user-config` 与 `--ignore-rules`；
- 危险 bypass 参数，但没有普通 approval 参数。

### Probe 2.1：非交互启动与机器可读结果

在新建的系统临时 Git 仓库中，以 `--ignore-user-config --ignore-rules --sandbox read-only --color never --json` 启动一次不需要工具的人工文本任务。进程无需人工终端输入，约 19 秒后以退出码 `0` 结束。

stdout 中按行取得以下 JSONL 事件序列：

1. `thread.started`，包含明确 thread id；
2. `turn.started`；
3. 一个 `item.completed` / `error`，内容是 Skill 描述因上下文预算被缩短的警告；
4. 一个 `item.completed` / `agent_message`，文本与人工标记完全一致；
5. `turn.completed`，包含 input、cached input、output 与 reasoning output token usage。

相关 stderr / 诊断流还出现：

- stdin 被视为额外输入来源的提示；
- 本地 model cache 缺少字段的解析错误。

尽管存在上述诊断与 JSONL `error` item，本轮仍有目标 Agent 消息、`turn.completed`、usage 和退出码 `0`。因此，单个字符串为 `error` 的 item 不能独立定义整次调用失败；Harness 至少需要联合判断事件层级、turn 终态与进程退出事实。

本轮还反证了“`--ignore-user-config` 等于完全纯净运行环境”的潜在推断：当前环境仍向运行注入了 Skill 相关上下文，并受本地 model cache 状态影响。它们没有阻止本轮最小任务完成，但已经成为输出解析与复验条件的一部分；Plugin 来源尚未确认，本项不读取内部配置来追查来源。

截至此处，没有观察到命令执行、文件变更、网络或外部服务调用事件。

### Probe 2.2：指定 session 连续输入

使用 Probe 2.1 的明确 thread id 执行 `codex exec resume <SESSION_ID>`，并要求在不调用工具的情况下返回上一轮人工标记。resume 事件中的 thread id 与首次执行完全一致，Agent 准确返回 `STARGAZING2_ONE_SHOT_OK`；随后产生 `turn.completed` 与 usage，进程退出码为 `0`。

另在新建的第二个临时 Git 仓库启动全新 session，询问其是否知道其他 session 的标记。新 session 取得不同 thread id，并返回 `NO_CROSS_SESSION_MARKER`。这个最小样例没有观察到跨 session 语义泄漏，但单次 Agent 自述不能证明所有内部上下文绝对隔离；文件与并发隔离仍需后续探针。

resume 仍输出同类 model cache 诊断。由于 resume help 没有直接 sandbox 参数，本轮只验证了无工具文本连续性，没有验证恢复轮的强制文件权限；提示词禁止工具和外部访问只是弱约束。

### Probe 2.3：结构化最终结果

在第三个临时 Git 仓库建立预定 JSON Schema，要求最终结果包含且仅包含：`work_status`（`completed` 或 `blocked`）、`result`、`reason`。

完成样例要求计算 `2+3`，Agent message 返回符合 schema 的 JSON：状态为 `completed`、结果为 `5`、原因为空；受阻样例要求使用一个未提供且禁止猜测的 `ORBIT_CODE`，返回状态为 `blocked`、结果为空并给出缺失输入原因。两次调用都产生 `turn.completed`、usage 和退出码 `0`。

这证明当前版本可以把完成与受阻的 Agent 语义声明加工成机器可解析的固定形状，但两类调用在 CLI 层面都是成功完成的 turn。`work_status` 仍是模型生成内容，需要发布者或上层语义逻辑理解和校验；它不是 CLI 对真实工作状态的客观认证，更不是程序化验收。

### Probe 2.4：临时 workspace 文件写入与 read-only 边界

在第四个临时 Git 仓库使用 `workspace-write`，要求只创建一个包含人工文本的文件。JSONL 中依次出现 `file_change` 和本地校验 `command_execution`，二者均为 `completed`；磁盘检查确认文件存在且内容正确，turn 完成并以退出码 `0` 结束。

在第五个临时 Git 仓库使用 `read-only`，请求创建另一个人工文件。Codex 的写入工具返回明确错误：写入被 read-only sandbox 和 approval settings 阻止；随后的只读命令确认目标文件不存在，外层磁盘检查也确认 absent。Agent 最终如实报告受阻，但整个 turn 仍为 `turn.completed` 且进程退出码为 `0`。

这证明本轮临时 workspace 内的写入允许/拒绝可以由 sandbox 强制并留下可解析事件，且“工具写入被拒绝”仍可能是一次正常完成的 Agent turn，而不是 CLI 调用故障。

同时出现一个关键限制：read-only Agent 在执行任务前读取了 workspace 外的本地 Skill 文件，命令成功。该行为并非本项主动设计的外部目录探针，却直接证明 `read-only` 不等于读取范围隔离，也不等于只能访问 `-C` 指定目录；它主要约束写入。本轮只直接观察到这一个 workspace 外 Skill 文件，没有测定完整可读范围。若未来 Harness 需要强制保密边界，必须依赖更外层的 OS / 容器隔离或其他已经验证的机制，不能只依赖此参数。

Skill 注入会占用输入上下文，JSONL 已直接给出“描述因 2% skills context budget 被缩短”的事件；当前 usage 受到额外注入影响，但没有形成可稳定对照的幅度基线。本项不读取内部配置追查来源，也不把单次 usage 外推为稳定成本基线。

### Probe 2.5：失败、正常受阻与进程级取消

使用一个不存在的全零 UUID 执行 `codex exec resume`。CLI 在约 1 秒后以退出码 `1` 结束，诊断明确说明找不到该 thread id 对应的 rollout；没有产生 `thread.started`、`turn.started`、Agent message 或工具事件。

在一个未初始化 Git 仓库的临时目录运行普通 `codex exec`，且没有使用 `--skip-git-repo-check`。CLI 立即以退出码 `1` 结束，诊断说明当前不在 trusted directory；同样没有进入 thread、turn 或 Agent 工具执行。

这两类调用故障可以在 Agent 工作开始前由非零退出和明确诊断识别。正常 blocked 已由 Probe 2.3 验证为 Agent 语义声明，无需重复。

进程级取消使用新的临时 Git 仓库和独立进程组：Agent 被要求只运行 `sleep 60`，父探针观察到对应 `command_execution` 已开始后发送 SIGTERM。整个进程组在有界时间内消失，没有留下 workspace 文件。

取消后的关键事实是：Codex 进程返回码为 `0`，但 JSONL 既没有 `turn.completed`，也没有 `turn.failed`；只存在 thread / turn 已开始和工具执行已开始的证据。官方非交互文档没有为这一情形提供事务性取消协议。因此 Harness 不能把退出码 `0` 单独视为成功，也不能把进程已消失视为工作失败；本轮必须分类为`结果未知`。据此应按保守边界认为：已经产生的 token 成本、内部 session 记录或潜在外部副作用不能由进程终止自动撤销，除非另有独立证据。

## 实验中途暂停原因

Probe 2.4 意外但明确地证明：`--sandbox read-only` 会阻止临时 workspace 写入，却不会把 Agent 的读取范围限制在 `-C` workspace；Agent 至少能够读取一个当前平台用户可读的 workspace 外本地 Skill 文件，本项没有测定完整可读范围。提示词中的“不要读取外部文件、不要联网”只能形成弱约束。

因此，在没有新增 OS / 容器隔离时，继续取消探针或两个并发 Agent 探针会再次暴露同一读取边界。该风险超出了开始实验前对“只在临时目录工作”的直观理解，必须先由用户知情决定：

1. 把该限制作为 Codex CLI 接入条件，本项以`有条件可行`暂结，并把取消、真实并发和强读取隔离保留为未决；
2. 用户明确接受本机 Codex 在后续人工样例中仍可能读取 workspace 外本地文件的风险，再继续取消与最小并发探针；所得结论仍不会宣称存在强读取隔离。

## 用户对暂停项的决定

用户于 `2026-09-02` 明确选择第二种路径：知情接受后续人工样例中的 Codex 仍可能读取 workspace 外本地文件，继续取消与最小并发探针。

该决定授权继续已经成文的受控探针，不改变已发现的产品边界，也不把弱提示约束升级为强读取隔离。实验继续限定为临时 workspace 和人工输入；不会主动测试其他本地文件、网络或真实外部系统。

### Probe 2.6：两个独立角色的最小并发

在两个新建的临时 Git workspace 中近同时启动两个 Codex 进程，每个进程使用自己的 read-only sandbox、人工标记和 session。启动后检查确认两个进程曾同时处于存活状态。

两个角色分别取得唯一且彼此不同的 thread id，各自准确返回自己的人工标记，均产生 `turn.completed`、无 `turn.failed`、退出码为 `0`。两个 workspace 都没有产生非 Git 文件，未观察到结果、thread id 或文件交叉。总墙钟时间约 8.4 秒。

这证明当前机器与版本可以最小并发运行两个独立 Codex 角色，没有在该样例中观察到共享上下文或 workspace 污染。它不是压力测试，不证明更高并发、长任务、公平调度、稳定吞吐、账户限流或生产容量。

## 结论矩阵

| 评估维度 | 观察结论 | Harness 可依赖程度 |
| --- | --- | --- |
| 非交互启动 | `codex exec` 无需人工终端操作即可完成任务 | 可依赖，但受安装、认证与服务可用性前提约束 |
| 机器可读输出 | stdout 提供 JSONL；可取得 thread、turn、item、usage | 可依赖结构形态，不能把任意 `error` item 单独解释为整次失败 |
| 最终结果 | Agent message 与结构化 schema 结果均可取得 | 是 Agent 语义输出，不是客观质量认证 |
| session 连续性 | 明确 thread id 可以 resume，并保留文本上下文 | 可作为同一逻辑角色的连续性基础；恢复轮 sandbox 强度未验证 |
| session 隔离 | 新 session 使用不同 id，最小样例未见语义串线 | 初步可用，不构成内部绝对隔离证明 |
| workspace 写入 | `workspace-write` 允许写；`read-only` 强制拒绝写 | 可对本轮 workspace 写入形成强制边界 |
| workspace 读取 | read-only Agent 实际读取了 workspace 外 Skill 文件 | 不能依赖 `-C` 或 read-only 建立强读取隔离 |
| 正常受阻 | schema 可返回 `work_status=blocked` | 机器可解析，但仍是 Agent 声明 |
| 调用前故障 | 无效 session 与非 Git 目录均非零退出且不进入 turn | 可确定性识别本轮两类故障 |
| 进程级取消 | 独立进程组可被终止且无进程/文件残留 | 只能证明本轮本地进程停止；不能撤销成本或外部副作用 |
| 取消后的终态 | 退出码为 `0`，但没有 `turn.completed` / `turn.failed` | 必须标记结果未知，不能仅凭退出码判断成功 |
| 最小并发 | 两个独立进程、workspace、thread 同时完成 | 最小可行，不代表生产容量 |
| 资源观察 | `turn.completed` 提供 token usage | 可做部分统计；环境注入影响成本，没有证明硬预算控制 |
| 用户环境隔离 | ignore flags 后仍有 Skill 上下文和 model cache 诊断 | 不能假定纯净运行环境；需要适配诊断与公开条件 |

## 成立条件与未覆盖范围

将 Codex CLI 用作 Harness 中的 Agent 角色底层主体，至少需要接受并处理以下条件：

1. Harness 必须联合解析 JSONL 事件、turn 终态、Agent message、stderr 与进程退出事实，不能仅看退出码或任意单个 error item；
2. 角色连续性应保存并使用明确 thread id，不能依赖 `--last` 这种进程外隐式选择；
3. 没有明确 `turn.completed` 或 `turn.failed` 的中断调用应进入结果未知，不得自动重试或伪造失败；
4. read-only 只能作为已验证的 workspace 写入限制。若 thread 需要强读取隔离或敏感资料边界，必须另行验证 OS、容器或其他外层机制；
5. `--ignore-user-config` 与 `--ignore-rules` 不足以保证无 Skill 上下文、无本地缓存诊断或固定 token 成本；接入层必须容忍非致命诊断，并公开环境影响；
6. JSON Schema 可以固定 Agent 声明形状，但不能替代发布者判断、评审、验收或其他语义治理；
7. 两个最小角色并发已跑通，更高并发、长任务、限流和容量需要在具有真实需求时另行验证。

本项没有验证：完整本地可读范围、强制断网、MCP / hook / plugin 的完整隔离、resume 后有效 sandbox、认证续期、服务限流、账户总预算硬限制、大规模并发、跨 Harness 重启恢复、真实外部副作用幂等与生产安全。它们不能因核心路径跑通而被视为可行。

## 当前结论

`有条件可行`。

Probe 2.1–2.6 已满足 Stargazing 2 的核心门槛：当前坐标下存在无需人工终端操作的非交互路径，能够发起工作、取得机器可解析事件与结果、保存明确 thread id、向同一上下文发送后续输入，并让两个独立角色最小并发运行。正常受阻与部分调用故障也具有可解析差异。

它不是无条件可行：read-only 不能提供 workspace 读取隔离；用户环境仍会注入 Skill 相关上下文和诊断；进程级取消可能得到“退出码为 0 但无 turn 终态”的未知结果；usage 只支持部分观察而非已证明的硬预算；最小并发不能外推生产容量。

因此当前建议是把 Codex CLI 保留为 Harness 的可行候选接入对象，并在未来设计中把上述边界作为必须公开和处理的条件，而不是为追求统一接口抹平这些事实。本项结论只适用于记录的日期与最小兼容性坐标；版本或关键环境变化后按 Stargazing 1 的原则局部复验。

Stargazing 2 完成不会自动开始 Stargazing 3。

## 资料来源

- [OpenAI 官方 Codex CLI 非交互模式文档](https://learn.chatgpt.com/docs/non-interactive-mode)
- [OpenAI 官方 Codex CLI 页面](https://learn.chatgpt.com/docs/codex/cli)
