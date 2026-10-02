from __future__ import annotations

import uuid
import datetime
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, ClassVar
from pydantic import BaseModel, ConfigDict, Field

from infercore.logger import logger
from infercore.agents.base import AgentTools
from infercore.intelligence_registry.base import BaseRegistry, Registry


class AgentInitializeError(Exception):
    pass


class AgentChannelError(Exception):
    pass


class TaskStatus(Enum):
    WAITING = "waiting"
    RUNNING = "running"
    DONE = "done"


class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: f"Task-{str(uuid.uuid4())[:8]}")
    task_name: str
    task_state: TaskStatus = TaskStatus.WAITING
    started_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
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
        if self.task_state == TaskStatus.DONE:
            self.completed_at = datetime.datetime.now()

    def mark_complete(self) -> None:
        logger.info(f"Task with id - {self.task_id} completed!")
        self.task_state = TaskStatus.DONE
        self._mark_completion_time()



class Agent(BaseModel):
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



class UserMessage(BaseModel):
    role: Roles = Roles.USER
    message: str = Field(description="Message of the user")


class AgentMessage(BaseModel):
    role: Roles = Roles.AGENT
    sender: str
    recipient: str
    message: Any
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    correlation_id: str | None = None
    parent_message_id: str | None = None
    metadata: dict[str, Any] | None = None


class AgentChannelWrite(BaseModel):
    recipient: str
    value: Any
    skip_none: bool = False
    mapper: Callable[[Any], Any] | None = None


class MasterAgent(Agent):
    model_config = ConfigDict(arbitrary_types_allowed=True)

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
    agent_channels: dict[str, list[AgentMessage]] = field(
        default_factory=dict, init=False
    )

    def __post_init__(self) -> None:
        if self.agents is None and self.core_agent is None:
            raise AgentInitializeError(
                "Either provide `agents` or `core_agent` to initialize InferCoreRuntime"
            )

        self.agents = self._resolve_source_agents()

        self._create_agent_mapping(self.agents)
        self._create_agent_channels(self.agents)
        self.agent_catalog = MappingProxyType(
            {agent.name: agent.description for agent in self.agents}
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

    def _create_agent_channels(self, source_agents: tuple[Agent, ...]) -> None:
        self.agent_channels = {agent.name: [] for agent in source_agents}

    def _validate_agent_name(self, agent_name: str) -> None:
        if self.agent_map is None or agent_name not in self.agent_map:
            raise AgentChannelError(f"Agent {agent_name!r} is not registered")

    def write_to_agent(
        self,
        *,
        sender: str,
        recipient: str,
        message: Any,
        correlation_id: str | None = None,
        parent_message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        self._validate_agent_name(sender)
        self._validate_agent_name(recipient)

        envelope = AgentMessage(
            sender=sender,
            recipient=recipient,
            message=message,
            correlation_id=correlation_id,
            parent_message_id=parent_message_id,
            metadata=metadata,
        )
        self.agent_channels[recipient].append(envelope)
        return envelope

    def channel_write(
        self,
        *,
        sender: str,
        writes: tuple[AgentChannelWrite, ...] | list[AgentChannelWrite],
    ) -> list[AgentMessage]:
        messages: list[AgentMessage] = []
        for write in writes:
            value = write.value
            if write.mapper is not None:
                value = write.mapper(value)
            if write.skip_none and value is None:
                continue

            messages.append(
                self.write_to_agent(
                    sender=sender,
                    recipient=write.recipient,
                    message=value,
                )
            )

        return messages

    def read_agent_channel(self, agent_name: str) -> tuple[AgentMessage, ...]:
        self._validate_agent_name(agent_name)
        return tuple(self.agent_channels[agent_name])

    def drain_agent_channel(self, agent_name: str) -> tuple[AgentMessage, ...]:
        self._validate_agent_name(agent_name)
        messages = tuple(self.agent_channels[agent_name])
        self.agent_channels[agent_name].clear()
        return messages

    def ainfer(self, messages, task_status: TaskStatus=TaskStatus.WAITING):
        """Logic to run agent inference"""
