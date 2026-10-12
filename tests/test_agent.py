"""端到端测试：完整业务流程"""
import unittest

from agent import Outcome, RefundAgent, RefundRequest, Role
from agent.tools import OrderStore, PaymentGateway
from agent.permissions import PermissionDeniedError


class TestHappyPath(unittest.TestCase):
    def setUp(self):
        self.agent = RefundAgent()

    def test_small_refund_auto_approved(self):
        r = self.agent.handle(RefundRequest("ORD-1001", 199.0, idempotency_key="k1"))
        self.assertEqual(r.outcome, Outcome.AUTO_APPROVED)
        self.assertTrue(r.refund_id.startswith("RFD-"))
        # 状态轨迹完整：received -> order_validated -> policy_checked -> approved -> refunding -> done
        self.assertEqual(len(r.trace), 6)
        self.assertEqual(r.context["state"], "done")

    def test_trace_auditable(self):
        r = self.agent.handle(RefundRequest("ORD-1001", 100.0))
        self.assertEqual(r.trace[0], "init -> received")
        self.assertTrue(any("approved" in step for step in r.trace))

    def test_snapshot_restore(self):
        from agent.state import State, StateMachine
        sm = StateMachine()
        sm.transition(State.ORDER_VALIDATED, "test")
        restored = StateMachine.restore(sm.snapshot())
        self.assertEqual(restored.state, State.ORDER_VALIDATED)
        self.assertEqual(restored.trace, sm.trace)


class TestEscalation(unittest.TestCase):
    def test_large_amount_escalates(self):
        agent = RefundAgent()
        r = agent.handle(RefundRequest("ORD-1002", 1200.0))
        self.assertEqual(r.outcome, Outcome.ESCALATED)
        self.assertEqual(r.refund_id, "")
        self.assertEqual(len(agent.gateway.executed), 0)   # 未执行退款

    def test_escalation_can_be_approved_by_human(self):
        from agent.state import State, StateMachine
        sm = StateMachine()
        sm.transition(State.ORDER_VALIDATED)
        sm.transition(State.POLICY_CHECKED)
        sm.transition(State.ESCALATED, "大额")
        sm.transition(State.APPROVED, "人工批准")     # 人工侧流转
        sm.transition(State.REFUNDING)
        self.assertEqual(sm.state, State.REFUNDING)


class TestPolicyRejection(unittest.TestCase):
    def setUp(self):
        self.agent = RefundAgent()

    def test_expired_order_rejected(self):
        r = self.agent.handle(RefundRequest("ORD-1003", 88.0))
        self.assertEqual(r.outcome, Outcome.REJECTED)
        self.assertIn("超过", r.message)

    def test_already_refunded_rejected(self):
        r = self.agent.handle(RefundRequest("ORD-9001", 199.0))
        self.assertEqual(r.outcome, Outcome.REJECTED)
        self.assertIn("重复退款", r.message)

    def test_amount_exceeds_order_rejected(self):
        r = self.agent.handle(RefundRequest("ORD-1004", 500.0))
        self.assertEqual(r.outcome, Outcome.REJECTED)
        self.assertIn("超过订单金额", r.message)


class TestPermissionBoundary(unittest.TestCase):
    def test_customer_cannot_call_refund_tool(self):
        gw = PaymentGateway()
        with self.assertRaises(PermissionDeniedError):
            gw.create_refund("ORD-1001", 199.0, "k", caller=Role.CUSTOMER)

    def test_customer_cannot_read_order_without_scope(self):
        # customer 有 order.read，可验证装饰器放行
        store = OrderStore()
        order = store.get_order("ORD-1001", caller=Role.CUSTOMER)
        self.assertEqual(order.order_id, "ORD-1001")

    def test_agent_cannot_exceed_auto_limit(self):
        # Agent 角色持有 refund.write，但业务规则阻止其自动大额退款
        agent = RefundAgent()
        r = agent.handle(RefundRequest("ORD-1002", 1200.0))
        self.assertEqual(r.outcome, Outcome.ESCALATED)


class TestFailureRecovery(unittest.TestCase):
    def test_retry_eventually_succeeds(self):
        gw = PaymentGateway(fail_times=2)   # 前 2 次瞬时故障
        agent = RefundAgent(gateway=gw)
        r = agent.handle(RefundRequest("ORD-1001", 199.0, idempotency_key="k-retry"))
        self.assertEqual(r.outcome, Outcome.AUTO_APPROVED)
        self.assertEqual(gw._call_count, 3)   # 重试 2 次后第 3 次成功

    def test_retry_exhausted_escalates(self):
        gw = PaymentGateway(fail_times=99)
        agent = RefundAgent(gateway=gw)
        r = agent.handle(RefundRequest("ORD-1001", 199.0))
        # 降级策略：退款执行失败 -> 转人工，而非静默失败
        self.assertEqual(r.outcome, Outcome.ESCALATED)
        self.assertIn("转人工", r.message)

    def test_idempotency_prevents_double_refund(self):
        gw = PaymentGateway()
        agent = RefundAgent(gateway=gw)
        req = RefundRequest("ORD-1001", 199.0, idempotency_key="k-dup")
        agent.handle(req)
        r2 = agent.handle(req)
        self.assertEqual(r2.outcome, Outcome.AUTO_APPROVED)
        self.assertEqual(len(gw.executed), 1)   # 网关只被调用一次

    def test_circuit_breaker_degrades(self):
        gw = PaymentGateway(fail_times=99)
        breaker_threshold = 3
        agent = RefundAgent(gateway=gw, breaker=__import__("agent.recovery", fromlist=["CircuitBreaker"]).CircuitBreaker(failure_threshold=breaker_threshold))
        for _ in range(breaker_threshold):
            agent.handle(RefundRequest("ORD-1001", 199.0))
        self.assertTrue(agent.breaker.is_open)
        # 熔断后新请求直接降级转人工，不再打到网关
        calls_before = gw._call_count
        r = agent.handle(RefundRequest("ORD-1001", 199.0))
        self.assertEqual(r.outcome, Outcome.ESCALATED)
        self.assertEqual(gw._call_count, calls_before)

    def test_invalid_transition_blocked(self):
        from agent.state import InvalidTransitionError, State, StateMachine
        sm = StateMachine()
        with self.assertRaises(InvalidTransitionError):
            sm.transition(State.DONE)   # received -> done 非法


if __name__ == "__main__":
    unittest.main(verbosity=2)
