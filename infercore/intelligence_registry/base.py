from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from infercore.agents.base import BaseAgent
from infercore.store.in_memory_registry import InMemoryRegistry
from infercore.store.registry_schema import Base, RegistryEntry


class DatabaseRegistryStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        Base.metadata.create_all(self._engine)

    @staticmethod
    def _serialize_tools(tools: Any) -> list[dict[str, Any]] | None:
        if tools is None:
            return None

        serialized_tools: list[dict[str, Any]] = []
        for tool in tools:
            serialized_tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                }
            )

        return serialized_tools

    @staticmethod
    def _serialize_metadata(agent: Any) -> dict[str, Any] | None:
        return getattr(agent, "metadata", None)

    def put(self, key: str, agent: Any) -> None:
        with Session(self._engine) as session:
            existing = session.query(RegistryEntry).filter_by(name=key).one_or_none()
            payload = {
                "name": key,
                "description": agent.description,
                "system_prompt": agent.system_prompt,
                "tools": self._serialize_tools(getattr(agent, "tools", None)),
                "entry_metadata": self._serialize_metadata(agent),
            }

            if existing is None:
                session.add(RegistryEntry(**payload))
            else:
                for field_name, value in payload.items():
                    setattr(existing, field_name, value)

            session.commit()

    def get(self, key: str) -> BaseAgent | None:
        with Session(self._engine) as session:
            entry = session.query(RegistryEntry).filter_by(name=key).one_or_none()
            if entry is None:
                return None

            from infercore.agents.agent_definations import Agent

            return Agent(
                name=entry.name,
                description=entry.description,
                system_prompt=entry.system_prompt,
                metadata=entry.entry_metadata,
            )


class BaseRegistry(ABC):
    def __init__(self, db_base: Engine | None = None) -> None:
        if db_base is None:
            self._store = InMemoryRegistry()

        else:
            self._store = DatabaseRegistryStore(db_base)

    @abstractmethod
    async def register(self, agent: BaseAgent) -> None:
        """Logic to register agent into the registry"""
        ...

    @abstractmethod
    async def fetch(self, agentID: str) -> BaseAgent | None:
        """Logic to fetch agent from the registry"""
        ...


class Registry(BaseRegistry):
    def __init__(self, db_base: Engine | None = None):
        """Registers the agent to registry."""
        super().__init__(db_base)

    async def register(self, agent: BaseAgent) -> None:
        self._store.put(agent.name, agent)

    async def fetch(self, agentID: str) -> BaseAgent:
        return self._store.get(agentID)
