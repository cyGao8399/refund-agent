"""权限边界：调用者角色 -> 工具 scope；业务规则（自动退款金额上限）

两层边界：
1. 工具层：每个工具声明所需 scope，调用者角色必须持有该 scope
2. 业务层：超过 auto_approve_limit 的申请不允许 Agent 自动执行，必须转人工
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Callable

from .models import Role


class PermissionDeniedError(Exception):
    pass


# 角色持有的 scope（最小权限原则）
ROLE_SCOPES: dict[Role, frozenset[str]] = {
    Role.CUSTOMER: frozenset({"order.read", "policy.read"}),
    Role.AGENT: frozenset({"order.read", "policy.read", "refund.write"}),
    Role.APPROVER: frozenset({"order.read", "policy.read", "refund.write"}),
}


def require_scope(scope: str) -> Callable:
    """工具方法装饰器：校验调用者角色是否持有 scope"""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            role: Role = kwargs.get("caller") or (args[-1] if args else None)
            if not isinstance(role, Role):
                raise PermissionDeniedError("缺少调用者角色，拒绝执行")
            if scope not in ROLE_SCOPES.get(role, frozenset()):
                raise PermissionDeniedError(
                    f"角色 {role.value} 缺少权限: {scope}"
                )
            return fn(self, *args, **kwargs)
        return wrapper
    return decorator


@dataclass
class ApprovalPolicy:
    """业务权限规则：Agent 自动退款上限"""
    auto_approve_limit: float = 500.0

    def need_manual_approval(self, amount: float) -> bool:
        return amount > self.auto_approve_limit
