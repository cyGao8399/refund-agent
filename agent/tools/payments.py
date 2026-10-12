"""支付网关工具（Mock，可注入故障用于测试失败恢复）"""
from __future__ import annotations

import itertools

from ..models import Role
from ..permissions import require_scope
from ..recovery import TransientError


class PaymentGateway:
    def __init__(self, fail_times: int = 0):
        """fail_times: 前 N 次调用抛出瞬时故障（模拟网络抖动），0 = 始终正常"""
        self._fail_times = fail_times
        self._call_count = 0
        self._ids = itertools.count(1)
        self.executed: list[tuple[str, float, str]] = []   # 审计记录

    @require_scope("refund.write")
    def create_refund(self, order_id: str, amount: float, idempotency_key: str, caller: Role) -> str:
        self._call_count += 1
        if self._call_count <= self._fail_times:
            raise TransientError(f"支付网关超时（第 {self._call_count} 次调用）")
        refund_id = f"RFD-{next(self._ids):04d}"
        self.executed.append((order_id, amount, idempotency_key))
        return refund_id
