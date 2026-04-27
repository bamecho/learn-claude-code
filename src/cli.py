import os

from dotenv import load_dotenv
from src.provider.anthropic_provider import AnthropicProvider
from src.tools.base import ToolRegistry
from src.tools.bash_tool import BashTool
from src.tools.file_tools import ReadFileTool, WriteFileTool, EditFileTool
from src.tools.todo_tool import TodoTool
from src.agent.agent import Agent


def main() -> None:
    load_dotenv(override=True)

    if os.getenv("ANTHROPIC_BASE_URL"):
        os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

    api_key = os.getenv("API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    base_url = os.getenv("BASE_URL") or os.getenv("ANTHROPIC_BASE_URL") or None
    model = os.getenv("MODEL") or os.getenv("MODEL_ID") or None

    if not api_key:
        print("Error: API_KEY not set. Please copy .env.example to .env and configure.")
        return

    provider = AnthropicProvider(api_key=api_key, base_url=base_url, model=model)
    registry = ToolRegistry()
    registry.register(BashTool())
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(EditFileTool())
    registry.register(TodoTool())

    system = (
        f"You are a coding agent at {os.getcwd()}. "
        "You have access to bash, read_file, write_file, edit_file, and todo tools. "
        "Use them to inspect and change the workspace. Act first, then report clearly. "
        "Use the todo tool for multi-step work. "
        "Keep exactly one step in_progress when a task has multiple steps. "
        "Refresh the plan as work advances. Prefer tools over prose."
    )
    agent = Agent(provider, registry, system=system)

    try:
        agent.run_interactive()
    except KeyboardInterrupt:
        print("\n再见！")


if __name__ == "__main__":
    main()
