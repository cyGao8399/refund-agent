"""退款政策校验工具（只读，任何持有 policy.read 的角色可调用）"""
from __future__ import annotations

from datetime import datetime

from ..models import Role
from ..permissions import require_scope
from .orders import Order


class PolicyChecker:
    """7 天无理由退款：已支付/已发货/已签收均可，超过 7 天拒绝，已退款拒绝"""

    window_days = 7

    @require_scope("policy.read")
    def check(self, order: Order, refund_amount: float, caller: Role) -> tuple[bool, str]:
        if order.refunded:
            return False, "订单已退款，不能重复退款"
        if refund_amount > order.amount:
            return False, f"退款金额 {refund_amount} 超过订单金额 {order.amount}"
        age = (datetime.now() - order.paid_at).days
        if age > self.window_days:
            return False, f"订单支付已超过 {self.window_days} 天（{age} 天），超出无理由退款窗口"
        return True, "符合退款政策"
