from __future__ import annotations

import uuid
import datetime
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, ClassVar

from infercore.logger import logger
from infercore.agents.base import AgentTools
from infercore.intelligence_registry.base import BaseRegistry


class AgentInitializeError(Exception):
    pass


class TaskStatus(Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


@dataclass
class Task:
    task_name: str

    task_state: TaskStatus = TaskStatus.pending
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    started_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    completed_at: datetime.datetime | None = None

    _locked_fields: ClassVar[set[str]] = {
        "task_id",
        "started_at",
    }

    def __setattr__(self, name: str, value: Any) -> None:
        if name in self._locked_fields and name in self.__dict__:
            raise AttributeError(f"Field {name!r} cannot be overridden once set")

        super().__setattr__(name, value)

    def __post_init__(self) -> None:
        logger.info(
            f"Initializing the task - {self.task_id} with name {self.task_name}"
        )

    def _mark_completion_time(self) -> None:
        if self.task_state == TaskStatus.completed:
            self.completed_at = datetime.datetime.now()

    def mark_complete(self) -> None:
        logger.info(f"Task with id - {self.task_id} completed!")
        self.task_state = TaskStatus.completed
        self._mark_completion_time()


@dataclass(frozen=True, kw_only=True)
class Agent:
    name: str
    description: str
    system_prompt: str
    tools: tuple[AgentTools, ...] | None = None
    metadata: dict[str, Any] | None = None


class Roles(Enum):
    USER = "user"
    AI = "ai"
    AGENT = "agent"
    TOOL = "tool"


from pydantic import BaseModel, Field


class UserMessage(BaseModel):
    role: Roles = Roles.USER
    message: str = Field(description="Message of the user")


@dataclass(frozen=True, kw_only=True)
class MasterAgent(Agent):
    agents: tuple[Agent, ...]
    registry: BaseRegistry | None = None


@dataclass(kw_only=True)
class InferCoreRuntime:
    workflow_id: str = field(default_factory=lambda: f"ICW-{str(uuid.uuid4())[:8]}")

    agents: tuple[Agent, ...] | None = None
    core_agent: MasterAgent | None = None
    agent_map: MappingProxyType | None = field(default=None, init=False)
    agent_catalog: MappingProxyType | None = field(default=None, init=False)
    agent_catelog: MappingProxyType | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.agents is None and self.core_agent is None:
            raise AgentInitializeError(
                "Either provide `agents` or `core_agent` to initialize InferCoreRuntime"
            )

        source_agents = self._resolve_source_agents()
        self.agents = source_agents

        self._create_agent_mapping(source_agents)
        self.agent_catalog = MappingProxyType(
            {agent.name: agent.description for agent in source_agents}
        )
        self.agent_catelog = self.agent_catalog

    def _resolve_source_agents(self) -> tuple[Agent, ...]:
        if self.core_agent is not None:
            return tuple(self.core_agent.agents)
        if self.agents is not None:
            return tuple(self.agents)
        return ()

    def _create_agent_mapping(self, source_agents: tuple[Agent, ...]) -> None:
        temp_agent_map: dict[str, Agent] = {
            agent.name: agent for agent in source_agents
        }

        self.agent_map = MappingProxyType(temp_agent_map)
