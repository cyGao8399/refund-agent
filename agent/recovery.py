"""失败恢复：重试（指数退避）、幂等、熔断降级"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


class TransientError(Exception):
    """瞬时故障（网络抖动、依赖超时），可重试"""


class PermanentError(Exception):
    """永久故障（参数错误、业务冲突），重试无意义"""


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.1      # 秒；测试用短延迟
    backoff_factor: float = 2.0
    retryable: tuple = (TransientError,)

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        delay = self.base_delay
        last_exc: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return fn(*args, **kwargs)
            except self.retryable as exc:
                last_exc = exc
                if attempt < self.max_attempts:
                    time.sleep(delay)
                    delay *= self.backoff_factor
        raise PermanentError(
            f"重试 {self.max_attempts} 次后仍失败: {last_exc}"
        ) from last_exc


class IdempotencyStore:
    """幂等存储：同一 key 只执行一次副作用，重复提交返回首次结果"""

    def __init__(self):
        self._results: dict[str, Any] = {}

    def execute(self, key: str, fn: Callable, *args, **kwargs) -> Any:
        if not key:
            return fn(*args, **kwargs)   # 无幂等键则不保证幂等
        if key in self._results:
            return self._results[key]
        result = fn(*args, **kwargs)
        self._results[key] = result
        return result

    def __contains__(self, key: str) -> bool:
        return key in self._results


@dataclass
class CircuitBreaker:
    """熔断器：依赖连续失败时断开，保护系统并触发降级"""
    failure_threshold: int = 3
    _failures: int = 0
    _open: bool = field(default=False, init=False)

    @property
    def is_open(self) -> bool:
        return self._open

    def on_success(self) -> None:
        self._failures = 0
        self._open = False

    def on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._open = True

    def guard(self) -> None:
        if self._open:
            raise PermanentError("熔断器已打开，依赖服务不可用，进入降级流程")
