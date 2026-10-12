"""CLI 演示入口：python main.py"""
from agent import Outcome, RefundAgent, RefundRequest

ICON = {
    Outcome.AUTO_APPROVED: "✅",
    Outcome.ESCALATED: "👤",
    Outcome.REJECTED: "🚫",
    Outcome.FAILED: "💥",
}


def demo(agent: RefundAgent, desc: str, req: RefundRequest) -> None:
    print(f"\n=== {desc} ===")
    print(f"申请: 订单 {req.order_id} / ¥{req.amount} / 幂等键 '{req.idempotency_key or '-'}'")
    r = agent.handle(req)
    print(f"结果: {ICON[r.outcome]} {r.outcome.value} — {r.message}" + (f"（退款单 {r.refund_id}）" if r.refund_id else ""))
    print("轨迹: " + " | ".join(r.trace))


if __name__ == "__main__":
    agent = RefundAgent()

    demo(agent, "场景1：小额订单，自动退款", RefundRequest("ORD-1001", 199.0, "七天无理由", idempotency_key="req-001"))
    demo(agent, "场景2：重复提交（幂等防重）", RefundRequest("ORD-1001", 199.0, "重复点击", idempotency_key="req-001"))
    demo(agent, "场景3：大额订单，转人工（权限边界）", RefundRequest("ORD-1002", 1200.0, "质量问题"))
    demo(agent, "场景4：超期订单，政策拒绝", RefundRequest("ORD-1003", 88.0, "不想要了"))
    demo(agent, "场景5：已退款订单，拒绝", RefundRequest("ORD-9001", 199.0, "再次申请"))
    demo(agent, "场景6：退款金额超过订单金额", RefundRequest("ORD-1004", 500.0, "测试"))

    print("\n网关审计记录（实际执行的退款调用）:")
    for order_id, amount, key in agent.gateway.executed:
        print(f"  {order_id} / ¥{amount} / 幂等键 '{key or '-'}'")
