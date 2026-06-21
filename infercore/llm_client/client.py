from __future__ import annotations

import inspect
import os
from typing import Any, Sequence, get_args, get_origin

from litellm import acompletion
from litellm.types.utils import ModelResponse

from infercore.agents.base import AgentTools

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "openrouter/openai/gpt-4o-mini"


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = base_url or os.getenv(
            "OPENROUTER_BASE_URL",
            DEFAULT_OPENROUTER_BASE_URL,
        )

        env_model = os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
        self.model = self._normalize_model_name(model or env_model)

        if not self.api_key:
            raise ValueError(
                "Missing API key. Pass `api_key` or set `OPENROUTER_API_KEY`."
            )

    @staticmethod
    def _normalize_model_name(model: str) -> str:
        if model.startswith("openrouter/"):
            return model
        return f"openrouter/{model}"

    @classmethod
    def _annotation_to_json_schema(cls, annotation: Any) -> dict[str, Any]:
        if annotation is inspect.Signature.empty:
            return {"type": "string"}

        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is list:
            item_annotation = args[0] if args else str
            return {
                "type": "array",
                "items": cls._annotation_to_json_schema(item_annotation),
            }

        if origin is dict:
            return {"type": "object"}

        if origin in {tuple, set}:
            item_annotation = args[0] if args else str
            return {
                "type": "array",
                "items": cls._annotation_to_json_schema(item_annotation),
            }

        if origin is not None and type(None) in args:
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                return cls._annotation_to_json_schema(non_none_args[0])
            return {
                "anyOf": [cls._annotation_to_json_schema(arg) for arg in non_none_args]
            }

        scalar_type_map: dict[Any, str] = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
        }

        if annotation in scalar_type_map:
            return {"type": scalar_type_map[annotation]}

        return {"type": "object"}

    @classmethod
    def _parameter_to_json_schema(
        cls,
        parameter: inspect.Parameter,
    ) -> dict[str, Any]:
        if parameter.annotation is not inspect.Signature.empty:
            return cls._annotation_to_json_schema(parameter.annotation)

        if parameter.default is not inspect.Signature.empty:
            return cls._annotation_to_json_schema(type(parameter.default))

        return {"type": "string"}

    @classmethod
    def _build_tool_parameters(cls, tool: AgentTools) -> dict[str, Any]:
        signature = inspect.signature(tool.func)
        properties: dict[str, Any] = {}
        required: list[str] = []

        for name, parameter in signature.parameters.items():
            if parameter.kind in {
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                continue

            properties[name] = cls._parameter_to_json_schema(parameter)
            if parameter.default is inspect.Signature.empty:
                required.append(name)

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema

    @classmethod
    def _normalize_tool(cls, tool: AgentTools | dict[str, Any]) -> dict[str, Any]:
        if isinstance(tool, AgentTools):
            return {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": cls._build_tool_parameters(tool),
                },
            }

        if isinstance(tool, dict):
            return tool

        raise TypeError(
            "Tools must be either OpenAI-compatible tool dictionaries or AgentTools instances."
        )

    async def infer(
        self,
        messages: Sequence[dict[str, Any]],
        tools: list[AgentTools | dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        completion_kwargs = dict(kwargs)
        if tools is not None:
            completion_kwargs["tools"] = [self._normalize_tool(tool) for tool in tools]

        return await acompletion(
            model=self.model,
            messages=list(messages),
            api_key=self.api_key,
            base_url=self.base_url,
            **completion_kwargs,
        )
