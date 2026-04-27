from typing import Protocol, runtime_checkable, Literal
from dataclasses import dataclass


@dataclass(frozen=True)
class ContentBlock:
    type: Literal["text", "tool_use"]
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict | None = None


@dataclass(frozen=True)
class LLMResponse:
    content: list[ContentBlock]
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "error"] | None
    usage: dict | None = None


@runtime_checkable
class LLMProvider(Protocol):
    def chat(self, messages: list[dict], tools: list[dict] | None = None, system: str | None = None) -> LLMResponse:
        """调用 LLM，返回统一格式的响应。"""
        ...
