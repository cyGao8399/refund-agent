"""数据模型定义"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(str, Enum):
    """调用者角色，用于权限边界"""
    CUSTOMER = "customer"    # 只能发起申请、查询
    AGENT = "agent"          # Agent 自身，可执行只读工具与小额退款
    APPROVER = "approver"    # 人工审批员，可执行大额退款


class Outcome(str, Enum):
    """退款申请最终处理结果"""
    AUTO_APPROVED = "auto_approved"    # 自动退款成功
    ESCALATED = "escalated"            # 转人工审批
    REJECTED = "rejected"              # 政策拒绝
    FAILED = "failed"                  # 执行失败（已重试，未退款）


@dataclass
class RefundRequest:
    """退款申请（业务入口）"""
    order_id: str
    amount: float
    reason: str = ""
    requested_by: Role = Role.CUSTOMER
    idempotency_key: str = ""          # 幂等键：同一键重复提交不会产生两次退款


@dataclass
class RefundResult:
    """处理结果"""
    outcome: Outcome
    message: str
    refund_id: str = ""
    trace: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
