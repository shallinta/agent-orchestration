# Stargazing 7 Probe 7.1

这是一个可丢弃的 Python 标准库实验，用于验证一个很窄的恢复窗口：Harness 已提交 Adapter 接受事实、尚无可靠终态时退出，新进程能否把该执行恢复为`result_unknown`，且不自动重新派发。

它不是产品存储层、工作流引擎、真实 Agent Adapter 或生产容灾实现。

## 自动验证

在仓库根目录运行：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s experiments/stargazing-007 -p 'test_*.py' -v
```

测试使用`TemporaryDirectory`保存 SQLite、WAL/SHM（如有）和 Adapter JSONL 账本，测试结束后自动清理。仓库中不应留下这些运行实例或 Python 缓存。

## 手工运行

在仓库根目录运行：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 experiments/stargazing-007/run_probe.py
```

Runner 在同一个临时目录内依次启动三个独立子进程：计划崩溃进程、首次恢复进程、二次恢复进程。所有子进程均通过参数数组且 `shell=False` 启动，并设置明确超时。

成功时只输出一行结构摘要：

```json
{"adapter_counts":{"accepted":1,"duplicate":0,"total":1},"fact_counts":{"acceptances":1,"agent_results":0,"attempts":1,"delegation_completions":0,"delegations":1,"events":6,"messages":0,"roles":2},"idempotent":true,"planned_crash_observed":true,"redispatch_count":0,"schema_version":"stargazing-007-probe-v1","states":{"dispatch":"accepted","recovery":"result_unknown","terminal":null},"unknown_event_count":1}
```

摘要不包含临时路径、原始数据库、环境变量、prompt、凭证、子进程 stdout/stderr 或任意业务文本。任一子进程超时、退出异常、输出不符合固定结构或事实不一致时，Runner 以非零状态静默失败，不转发可能敏感的子进程内容。

## 清理与结论边界

命令退出时，Runner 拥有的临时目录会自动删除；无需手动删除数据库、账本、WAL 或 SHM 文件。如果进程被外部强制终止，操作系统临时目录可能暂时保留运行文件，应按临时文件策略清理，不能提交到 Git。

本实验只验证三个 Python 进程依次运行时，已经提交的 SQLite 事实可被后续进程重开读取。它不模拟突然断电、操作系统崩溃、磁盘缓存丢失、文件系统损坏或数据库硬件故障，因此“进程重启后可恢复”不等于已经证明断电耐久、生产容灾或高可用。
