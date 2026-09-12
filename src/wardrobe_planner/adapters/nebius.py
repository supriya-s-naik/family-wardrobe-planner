from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from pydantic import BaseModel

from wardrobe_planner.config import Settings
from wardrobe_planner.domain.plans import ToolSmokeResult


class NebiusModel:
    """Small OpenAI-compatible boundary around Nebius Token Factory."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.client = OpenAI(
            api_key=self.settings.nebius_api_key,
            base_url=self.settings.nebius_base_url,
            timeout=120.0,
            max_retries=0,
        )

    def choose_tool(
        self,
        *,
        user_message: str,
        tools: list[dict[str, Any]],
        expected_tool: str,
    ) -> ToolSmokeResult:
        response = self.client.chat.completions.create(
            model=self.settings.nebius_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You route wardrobe-planning requests to tools. "
                        "Call exactly one appropriate tool and do not answer in prose."
                    ),
                },
                {"role": "user", "content": user_message},
            ],
            tools=tools,
            tool_choice="auto",
            temperature=0,
        )
        calls = response.choices[0].message.tool_calls or []
        if len(calls) != 1:
            raise RuntimeError(f"Expected one tool call, received {len(calls)}")
        call = calls[0]
        arguments = json.loads(call.function.arguments)
        return ToolSmokeResult(
            expected_tool=expected_tool,
            actual_tool=call.function.name,
            arguments=arguments,
        )

    def decide_tool(
        self,
        *,
        system_prompt: str,
        user_message: str,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        calls = self.decide_tools(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=tools,
        )
        if not calls:
            return None
        if len(calls) > 1:
            raise RuntimeError(f"Expected at most one tool call, received {len(calls)}")
        return calls[0]

    def decide_tools(
        self,
        *,
        system_prompt: str,
        user_message: str,
        tools: list[dict[str, Any]],
        tool_choice: str | dict[str, Any] = "auto",
    ) -> list[dict[str, Any]]:
        response = self.client.chat.completions.create(
            model=self.settings.nebius_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=True,
            temperature=0,
        )
        calls = response.choices[0].message.tool_calls or []
        return [
            {
                "name": call.function.name,
                "arguments": json.loads(call.function.arguments),
                "reason": f"Nebius selected {call.function.name} from the available tools.",
            }
            for call in calls
        ]

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_message: str,
        response_model: type[BaseModel],
        schema_name: str,
    ) -> BaseModel:
        schema = _strict_json_schema(response_model.model_json_schema())
        response = self.client.chat.completions.create(
            model=self.settings.nebius_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
            temperature=0,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Nebius returned no structured content")
        return response_model.model_validate_json(content)

    def generate_via_tool(
        self,
        *,
        system_prompt: str,
        user_message: str,
        response_model: type[BaseModel],
        tool_name: str,
        tool_description: str,
    ) -> BaseModel:
        schema = _strict_json_schema(response_model.model_json_schema())
        response = self.client.chat.completions.create(
            model=self.settings.nebius_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": tool_description,
                        "parameters": schema,
                        "strict": True,
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": tool_name}},
            temperature=0,
            max_tokens=3500,
        )
        calls = response.choices[0].message.tool_calls or []
        if len(calls) != 1 or calls[0].function.name != tool_name:
            raise RuntimeError(f"Nebius did not call required tool {tool_name}")
        return response_model.model_validate_json(calls[0].function.arguments)


def _strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make every object closed and every declared property required."""
    if schema.get("type") == "object" and "properties" in schema:
        properties = schema["properties"]
        schema["additionalProperties"] = False
        schema["required"] = list(properties)
    for value in schema.values():
        if isinstance(value, dict):
            _strict_json_schema(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _strict_json_schema(item)
    return schema
