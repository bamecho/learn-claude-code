from anthropic import Anthropic
from .base import LLMProvider, LLMResponse, ContentBlock


class AnthropicProvider:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.client = Anthropic(api_key=api_key, base_url=base_url)
        self.model = model or "claude-3-5-sonnet-20241022"

    def chat(self, messages: list[dict], tools: list[dict] | None = None, system: str | None = None, max_tokens: int | None = None) -> LLMResponse:
        try:
            kwargs: dict = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens if max_tokens is not None else 4096,
            }
            if tools:
                kwargs["tools"] = tools
            if system:
                kwargs["system"] = system

            response = self.client.messages.create(**kwargs)

            content_blocks: list[ContentBlock] = []
            for block in response.content:
                if block.type == "text":
                    content_blocks.append(
                        ContentBlock(type="text", text=block.text)
                    )
                elif block.type == "tool_use":
                    content_blocks.append(
                        ContentBlock(
                            type="tool_use",
                            id=block.id,
                            name=block.name,
                            input=block.input,
                        )
                    )

            stop_reason = response.stop_reason
            if stop_reason not in ("end_turn", "tool_use", "max_tokens"):
                stop_reason = None

            usage = None
            if response.usage:
                usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                }

            return LLMResponse(
                content=content_blocks,
                stop_reason=stop_reason,
                usage=usage,
            )
        except Exception as exc:
            return LLMResponse(
                content=[ContentBlock(type="text", text=f"Error: {exc}")],
                stop_reason="error",
                usage=None,
            )
