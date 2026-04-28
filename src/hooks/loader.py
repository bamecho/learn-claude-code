import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(".hooks.json")


def load_hooks(config_path: Path | str | None = None) -> dict[str, list[dict]]:
    """Load hook definitions from a JSON config file.

    Expected format:
    {
      "hooks": {
        "PreToolUse": [
          {"command": "echo test", "matcher": "*"}
        ]
      }
    }

    Returns a dict mapping event_name -> list of hook definition dicts.
    """
    config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if not config_path.exists():
        logger.warning("Hook config not found: %s", config_path)
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        logger.error("Invalid hook config JSON: %s", exc)
        return {}

    if not isinstance(config, dict):
        logger.error("Hook config must be a JSON object")
        return {}

    hooks = config.get("hooks", {})
    if not isinstance(hooks, dict):
        logger.error("Hook config 'hooks' must be an object")
        return {}

    return {k: v for k, v in hooks.items() if isinstance(v, list)}
