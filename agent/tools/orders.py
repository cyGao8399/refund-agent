"""订单服务工具（Mock 数据源，模拟真实 DB）"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..models import Role
from ..permissions import require_scope
from ..recovery import PermanentError


@dataclass
class Order:
    order_id: str
    amount: float
    status: str            # paid / shipped / delivered
    paid_at: datetime
    refunded: bool = False


class OrderStore:
    def __init__(self):
        now = datetime.now()
        self._orders: dict[str, Order] = {
            "ORD-1001": Order("ORD-1001", 199.0, "delivered", now - timedelta(days=2)),
            "ORD-1002": Order("ORD-1002", 1200.0, "delivered", now - timedelta(days=1)),
            "ORD-1003": Order("ORD-1003", 88.0, "delivered", now - timedelta(days=30)),
            "ORD-1004": Order("ORD-1004", 66.0, "paid", now - timedelta(days=1)),
            "ORD-9001": Order("ORD-9001", 199.0, "delivered", now - timedelta(days=2), refunded=True),
        }

    @require_scope("order.read")
    def get_order(self, order_id: str, caller: Role) -> Order:
        order = self._orders.get(order_id)
        if not order:
            raise PermanentError(f"订单不存在: {order_id}")
        return order

    @require_scope("order.read")
    def list_orders(self, caller: Role) -> list[Order]:
        return list(self._orders.values())

    @require_scope("order.read")
    def is_refunded(self, order_id: str, caller: Role) -> bool:
        return self._orders[order_id].refunded
