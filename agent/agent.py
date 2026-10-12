"""退款审批 Agent：编排工具调用、状态机、权限与失败恢复

业务目标：自动处理客户退款申请
  1. 校验订单（存在性、金额）
  2. 政策校验（7 天无理由窗口）
  3. 金额 <= 上限：自动退款（重试 + 幂等 + 熔断保护）
     金额 >  上限：转人工审批（权限边界，Agent 不越权）
  4. 全程状态机留痕，可随时快照/恢复
"""
from __future__ import annotations

from .models import Outcome, RefundRequest, RefundResult, Role
from .permissions import ApprovalPolicy, PermissionDeniedError
from .recovery import (
    CircuitBreaker,
    IdempotencyStore,
    PermanentError,
    RetryPolicy,
)
from .state import State, StateMachine
from .tools import OrderStore, PaymentGateway, PolicyChecker, ToolRegistry


class RefundAgent:
    def __init__(
        self,
        orders: OrderStore | None = None,
        policy: PolicyChecker | None = None,
        gateway: PaymentGateway | None = None,
        approval: ApprovalPolicy | None = None,
        retry: RetryPolicy | None = None,
        breaker: CircuitBreaker | None = None,
        idempotency: IdempotencyStore | None = None,
    ):
        self.orders = orders or OrderStore()
        self.policy = policy or PolicyChecker()
        self.gateway = gateway or PaymentGateway()
        self.approval = approval or ApprovalPolicy()
        self.retry = retry or RetryPolicy()
        self.breaker = breaker or CircuitBreaker()
        self.idempotency = idempotency or IdempotencyStore()

        self.registry = ToolRegistry()
        self.registry.register("get_order", "查询订单", self.orders.get_order)
        self.registry.register("check_policy", "退款政策校验", self.policy.check)
        self.registry.register("create_refund", "创建退款单", self.gateway.create_refund)

    def handle(self, request: RefundRequest) -> RefundResult:
        sm = StateMachine()
        try:
            # ---- 1. 订单校验 ----
            order = self.registry.invoke(
                "get_order", request.order_id, caller=Role.AGENT
            )
            if request.amount > order.amount:
                sm.transition(State.REJECTED, "退款金额超过订单金额")
                return self._result(sm, Outcome.REJECTED, "退款金额超过订单金额")
            sm.transition(State.ORDER_VALIDATED, f"订单 {order.order_id} 校验通过")

            # ---- 2. 政策校验 ----
            ok, msg = self.registry.invoke(
                "check_policy", order, request.amount, caller=Role.AGENT
            )
            if not ok:
                sm.transition(State.REJECTED, msg)
                return self._result(sm, Outcome.REJECTED, msg)
            sm.transition(State.POLICY_CHECKED, "政策校验通过")

            # ---- 3. 权限边界：金额超限转人工 ----
            if self.approval.need_manual_approval(request.amount):
                sm.transition(State.ESCALATED, f"金额 {request.amount} 超过自动审批上限")
                return self._result(
                    sm, Outcome.ESCALATED,
                    f"金额 {request.amount} 超过自动审批上限 {self.approval.auto_approve_limit}，已转人工审批",
                )
            sm.transition(State.APPROVED, "Agent 自动批准")

            # ---- 4. 执行退款（熔断 -> 重试 -> 幂等）----
            sm.transition(State.REFUNDING)
            refund_id = self._execute_refund(request)
            sm.transition(State.DONE, f"退款单 {refund_id} 创建成功")
            return self._result(sm, Outcome.AUTO_APPROVED, "退款成功", refund_id)

        except PermissionDeniedError as exc:
            return self._result(sm, Outcome.FAILED, f"权限拒绝: {exc}")
        except PermanentError as exc:
            # 重试耗尽或熔断：进入降级（转人工），而不是静默失败
            if sm.state in (State.REFUNDING, State.APPROVED):
                try:
                    sm.transition(State.ESCALATED, "退款执行失败，降级转人工")
                    return self._result(sm, Outcome.ESCALATED, f"退款执行失败，已转人工处理: {exc}")
                except Exception:
                    pass
            try:
                sm.transition(State.FAILED, str(exc))
            except Exception:
                pass
            return self._result(sm, Outcome.FAILED, str(exc))

    def _execute_refund(self, request: RefundRequest) -> str:
        """熔断保护 + 指数退避重试 + 幂等防重"""
        self.breaker.guard()
        try:
            refund_id = self.idempotency.execute(
                request.idempotency_key,
                lambda: self.retry.call(
                    self.registry.invoke,
                    "create_refund",
                    request.order_id,
                    request.amount,
                    request.idempotency_key,
                    caller=Role.AGENT,
                ),
            )
        except Exception:
            self.breaker.on_failure()
            raise
        self.breaker.on_success()
        return refund_id

    @staticmethod
    def _result(sm: StateMachine, outcome: Outcome, message: str, refund_id: str = "") -> RefundResult:
        return RefundResult(
            outcome=outcome,
            message=message,
            refund_id=refund_id,
            trace=list(sm.trace),
            context=sm.snapshot(),
        )
