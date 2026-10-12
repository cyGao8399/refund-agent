"""工具调用框架：注册器 + 统一调用入口"""
from __future__ import annotations

from typing import Any, Callable


class ToolRegistry:
    """工具注册器：集中管理工具名称、描述与调用，便于审计与扩展"""

    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(self, name: str, description: str, fn: Callable) -> None:
        self._tools[name] = {"description": description, "fn": fn}

    def invoke(self, name: str, *args, **kwargs) -> Any:
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"未知工具: {name}")
        return tool["fn"](*args, **kwargs)

    def describe(self) -> list[dict]:
        return [
            {"name": n, "description": t["description"]}
            for n, t in sorted(self._tools.items())
        ]
