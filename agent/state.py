"""状态管理：显式状态机 + 上下文快照 + 审计日志

设计要点：
- 所有状态流转必须通过 transition()，非法流转直接抛错（状态即权限）
- 上下文可随时序列化，支持中断后恢复（恢复即重新加载 state 对象）
- 每一步流转写入 trace，可完整回放处理过程
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class State(str, Enum):
    RECEIVED = "received"                  # 已受理
    ORDER_VALIDATED = "order_validated"    # 订单校验通过
    POLICY_CHECKED = "policy_checked"      # 政策校验完成
    APPROVED = "approved"                  # 已批准（自动或人工）
    REFUNDING = "refunding"                # 退款执行中
    DONE = "done"                          # 完成（自动退款成功）
    ESCALATED = "escalated"                # 已转人工
    REJECTED = "rejected"                  # 已拒绝
    FAILED = "failed"                      # 失败终态


# 合法流转表：状态 = 权限边界，未列出的流转一律禁止
TRANSITIONS: dict[State, set[State]] = {
    State.RECEIVED: {State.ORDER_VALIDATED, State.REJECTED, State.ESCALATED},
    State.ORDER_VALIDATED: {State.POLICY_CHECKED, State.REJECTED, State.ESCALATED},
    State.POLICY_CHECKED: {State.APPROVED, State.REJECTED, State.ESCALATED},
    State.APPROVED: {State.REFUNDING},
    State.REFUNDING: {State.DONE, State.FAILED, State.ESCALATED},
    # 终态
    State.DONE: set(),
    State.REJECTED: set(),
    State.FAILED: set(),
    # 转人工后人工侧独立流转：escalated -> approved
    State.ESCALATED: {State.APPROVED, State.REJECTED},
}


class InvalidTransitionError(Exception):
    pass


class StateMachine:
    def __init__(self, initial: State = State.RECEIVED):
        self.state = initial
        self.context: dict[str, Any] = {}
        self.trace: list[str] = [f"init -> {initial.value}"]

    def transition(self, target: State, note: str = "") -> None:
        allowed = TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise InvalidTransitionError(
                f"非法状态流转: {self.state.value} -> {target.value}"
            )
        self.trace.append(f"{self.state.value} -> {target.value}" + (f" ({note})" if note else ""))
        self.state = target

    def set(self, key: str, value: Any) -> None:
        self.context[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)

    def snapshot(self) -> dict:
        """序列化快照，用于持久化与断点恢复"""
        return {
            "state": self.state.value,
            "context": dict(self.context),
            "trace": list(self.trace),
        }

    @classmethod
    def restore(cls, snapshot: dict) -> "StateMachine":
        sm = cls(State(snapshot["state"]))
        sm.context = dict(snapshot.get("context", {}))
        sm.trace = list(snapshot.get("trace", []))
        return sm
