import os
from dotenv import load_dotenv
from src.provider.anthropic_provider import AnthropicProvider
from src.tools.base import ToolRegistry
from src.tools.mock_tools import MockFileReadTool
from src.agent.agent import Agent


def main() -> None:
    load_dotenv()
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL") or None
    model = os.getenv("MODEL") or None

    if not api_key:
        print("Error: API_KEY not set. Please copy .env.example to .env and configure.")
        return

    provider = AnthropicProvider(api_key=api_key, base_url=base_url, model=model)
    registry = ToolRegistry()
    registry.register(MockFileReadTool())

    agent = Agent(provider, registry)

    try:
        agent.run_interactive()
    except KeyboardInterrupt:
        print("\n再见！")


if __name__ == "__main__":
    main()
