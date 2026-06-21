from __future__ import annotations

from typing import Callable, Any
from pydantic import BaseModel


class AgentTools(BaseModel):
    name: str
    description: str
    func: Callable

    def execute_func(self, kwargs: dict[str, Any]) -> Any:
        return self.func(**kwargs)


class BaseAgent(BaseModel):
    """Base Agent"""

    name: str
    description: str
