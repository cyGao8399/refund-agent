# 🤖 退款审批 Agent（Refund Approval Agent）

一个围绕明确业务目标运行的 Python Agent 参考实现：**自动处理客户退款申请**。

- 小额退款（≤ ¥500）：自动校验、自动执行
- 大额退款（> ¥500）：转人工审批（Agent 不越权）
- 不符合政策：自动拒绝并说明原因

纯标准库实现（**零第三方依赖**），`unittest` 测试覆盖核心业务路径。

## 🎯 业务目标

```
客户提交退款申请
   │
   ▼
[1] 订单校验（存在性、金额、状态）
   │
   ▼
[2] 政策校验（7 天无理由窗口、未退款过）
   │
   ├── 不通过 ──→ 🚫 拒绝（附原因）
   │
   ▼
[3] 权限判断：金额 ≤ 500？
   │
   ├── 否 ──→ 👤 转人工审批（终态，人工侧独立流转）
   │
   ▼ 是
[4] 执行退款（熔断保护 → 指数退避重试 → 幂等防重）
   │
   ├── 成功 ──→ ✅ 完成
   └── 重试耗尽 ──→ 👤 降级转人工（不静默失败）
```

## 🧩 五大能力对照

| 要求 | 实现 | 位置 |
| --- | --- | --- |
| **工具调用** | `ToolRegistry` 统一注册/调用 + 权限装饰器 | `agent/tools/` |
| **状态管理** | 显式状态机：合法流转表约束 + 上下文快照/恢复 + 全程 trace 审计 | `agent/state.py` |
| **权限边界** | 两层：工具 scope（角色最小权限）+ 业务规则（自动退款金额上限） | `agent/permissions.py` |
| **失败恢复** | 指数退避重试、幂等存储（防重复退款）、熔断降级（重试耗尽转人工） | `agent/recovery.py` |
| **测试** | 16 个 unittest 用例，全部通过 | `tests/` |

## 🚀 快速开始

```bash
# 运行测试（16 个用例）
python -m unittest discover -s tests -v

# 运行 CLI 演示（6 个业务场景）
python main.py
```

要求 Python ≥ 3.10（使用了 `X | None` 类型语法）。

## 📁 项目结构

```
refund-agent/
├── main.py                 # CLI 演示入口（6 个业务场景）
├── agent/
│   ├── agent.py            # RefundAgent 主循环：编排工具/状态/权限/恢复
│   ├── models.py           # 数据模型（请求/结果/角色/结论）
│   ├── state.py            # 状态机：流转表 + 快照/恢复 + 审计 trace
│   ├── permissions.py      # 权限边界：role->scope 映射 + 审批金额策略
│   ├── recovery.py         # 失败恢复：重试/幂等/熔断
│   └── tools/
│       ├── base.py         # 工具注册器
│       ├── orders.py       # 订单服务（Mock 数据源）
│       ├── policy.py       # 退款政策校验
│       └── payments.py     # 支付网关（可注入故障）
└── tests/
    └── test_agent.py       # 16 个测试用例
```

## 🔑 设计要点

**状态即权限**：状态机使用显式流转表（`TRANSITIONS`），未列出的流转一律抛 `InvalidTransitionError`——Agent 不可能跳过政策校验直接执行退款，这是结构性保证而非约定。

**降级优于失败**：退款执行重试耗尽或熔断打开时，流转到 `escalated` 转人工，绝不静默丢单（见 `test_retry_exhausted_escalates`、`test_circuit_breaker_degrades`）。

**幂等防重**：同一 `idempotency_key` 的重复提交只执行一次网关调用（见 `test_idempotency_prevents_double_refund`）。

**Mock 即接口**：订单/支付均为可注入依赖，`PaymentGateway(fail_times=N)` 可模拟任意次数的网络故障，故障恢复路径因此可测试。

## 🤝 扩展方向

- 接入 LLM 做意图识别（当前规则驱动，行为完全确定）
- 状态快照持久化到 SQLite，实现跨进程断点恢复
- 人工审批回调接口（escalated → approved）
- 异步队列（把 refunding 状态挂起，回调驱动流转）

## 📄 License

[MIT](LICENSE) © 2026
