# Stargazing 5 / Probe 5.1–5.4

这是 **throwaway experiment code**：它只为 Probe 5.1–5.4 提供人工事实与协议证据，不是正式 Harness、领域模型、鉴权方案、持久化设计或生产服务。

`harness_server.py` 仅使用 Python 标准库。每个进程固定把调用者绑定为 `probe-caller`，工具参数不能声明或改写调用者身份。内存中预置：

- `allowed-worker`：可接收消息，也可接收委托；
- `forbidden-worker`：存在，但不可接收来自固定调用者的委托；
- `missing-worker`：不存在，用于稳定验证 `not_found`。

服务通过 newline-delimited JSON-RPC 2.0 STDIO 暴露 `initialize`、`notifications/initialized`、`ping`、`tools/list`、`tools/call`，工具只有 `query_thread`、`send_message` 与 `publish_delegation`。`tools/list` 接受 JSON-RPC `_meta` 与可选的字符串 `cursor`；`tools/call` 同样接受协议级 `_meta`，但不会因此放宽工具 `arguments` schema 或允许外层身份字段。服务不会读取或记录这些协议元数据的值。stdout 只承载协议响应；`--log` 指定的 JSONL 只记录固定服务端归因、request id、服务端枚举结果和归一化事实，不记录工具名或目标等 Agent 可控原值，也不记录消息、任务、身份注入值或凭据值。

## 运行测试

从仓库根目录运行：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v -s experiments/stargazing-005 -p 'test_*.py'
```

## Probe 5.1–5.2：STDIO MCP smoke

下面这段命令使用 `mktemp` 建立本次唯一日志目录，完成初始化、初始化通知、`ping`、工具列表和省略 `arguments` 的人工 thread 查询。协议响应写到 stdout；最后两行会显示本次日志路径和脱敏 JSONL，可在检查后删除整个临时目录：

```sh
PROBE_LOG_DIR="$(mktemp -d -t stargazing-005-smoke)"
PROBE_LOG_PATH="$PROBE_LOG_DIR/server-facts.jsonl"
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"direct-smoke","version":"1"}}}' '{"jsonrpc":"2.0","method":"notifications/initialized"}' '{"jsonrpc":"2.0","id":2,"method":"ping","params":{}}' '{"jsonrpc":"2.0","id":3,"method":"tools/list","params":{}}' '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"query_thread"}}' | python3 experiments/stargazing-005/harness_server.py --log "$PROBE_LOG_PATH"
printf 'redacted JSONL: %s\n' "$PROBE_LOG_PATH"
sed -n '1,5p' "$PROBE_LOG_PATH"
```

测试和 smoke 都不会启动 Codex CLI 或 Claude Code CLI，也不会连接外部服务。服务退出后内存中的消息与委托即丢失。

## Probe 5.3：capability CLI 与 loopback HTTP

`capability_probe.py` 的服务端 registry 只保存公开固定人工 capability 的 SHA-256 与固定 caller role 映射。它只模拟单角色 capability 的映射和拒绝，不验证随机性、保密性、短期生命周期、轮换或撤销，不能作为真实凭据方案。专用 CLI 只从 `SG5_CAPABILITY` 读取 capability，不提供 caller/role 参数；HTTP factory 只绑定 `127.0.0.1` 和 OS 分配的端口 `0`。HTTP 测试会显式 shutdown、close 并等待线程退出，不留下长期进程。

```sh
PROBE_LOG_DIR="$(mktemp -d -t stargazing-005-capability)"
SG5_CAPABILITY='sg5-synthetic-capability-v1' python3 experiments/stargazing-005/capability_probe.py cli --log "$PROBE_LOG_DIR/facts.jsonl" query_thread --arguments '{}'
```

## Probe 5.4：结构化返回请求 driver

`structured_request.schema.json` 为当前严格结构化输出兼容性实验刻意收缩为唯一的`query_thread + 空 arguments`请求；顶层只允许 `tool` 与 `arguments`，两个对象层都显式禁止额外字段。`structured_request_driver.py` 从 driver 参数选择已登记 execution attempt，并由该服务端映射绑定 caller；Agent 返回内容不能提供 caller 或 execution attempt。这个收缩只影响 Probe 5.4 的最小往返，不表示未来公共能力只包含查询。

```sh
PROBE_LOG_DIR="$(mktemp -d -t stargazing-005-structured)"
printf '%s' '{"tool":"query_thread","arguments":{}}' | python3 experiments/stargazing-005/structured_request_driver.py --log "$PROBE_LOG_DIR/facts.jsonl" --execution-attempt sg5-structured-attempt-1
```

这些直接协议与 driver 测试不构成 Codex/Claude 的 Agent E2E、原 session 结果回送、正式鉴权、token 轮换、TLS/OAuth、恶意同 OS 用户隔离、持久化、崩溃恢复、幂等或安全重试保证。
