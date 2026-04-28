import json
import logging
import os
import subprocess
from pathlib import Path

from src.hooks.loader import load_hooks

logger = logging.getLogger(__name__)

HOOK_EVENTS = ("PreToolUse", "PostToolUse", "SessionStart")
HOOK_TIMEOUT = 30
HOOK_DISPLAY_LIMIT = 200


class HookRunner:
    def __init__(
        self,
        config_path: Path | str | None = None,
        sdk_mode: bool = False,
        workdir: Path | str | None = None,
    ):
        self.hooks: dict[str, list[dict]] = {event: [] for event in HOOK_EVENTS}
        self._sdk_mode = sdk_mode
        self._workdir = Path(workdir) if workdir else Path.cwd()

        config = load_hooks(config_path)
        for event in HOOK_EVENTS:
            self.hooks[event] = config.get(event, [])

    def _check_workspace_trust(self) -> bool:
        if self._sdk_mode:
            return True
        trust_marker = self._workdir / ".claude" / ".claude_trusted"
        return trust_marker.exists()

    def _build_env(self, event: str, context: dict | None) -> dict[str, str]:
        env = dict(os.environ)
        if not context:
            return env

        tool_input = context.get("tool_input", {})
        if not isinstance(tool_input, dict):
            tool_input = {}

        env["HOOK_EVENT"] = event
        env["HOOK_TOOL_NAME"] = str(context.get("tool_name", ""))
        env["HOOK_TOOL_INPUT"] = json.dumps(tool_input, ensure_ascii=False)[:10000]
        env["HOOK_TOOL_COMMAND"] = str(tool_input.get("command", ""))
        env["HOOK_FILE_PATH"] = str(tool_input.get("filePath", tool_input.get("path", "")))
        if "tool_output" in context:
            env["HOOK_TOOL_OUTPUT"] = str(context.get("tool_output", ""))[:10000]
        return env

    def _print_hook_output(self, event: str, label: str, output: str) -> None:
        message = output.strip()
        if message:
            print(f"  [hook:{event}] {label}{message[:HOOK_DISPLAY_LIMIT]}", flush=True)

    def run(self, event: str, context: dict | None = None) -> dict:
        """Execute all hooks for an event.

        Returns:
            {
                "blocked": bool,
                "messages": list[str],
                "block_reason": str,
                "permission_override": str | None,
            }
        """
        result = {
            "blocked": False,
            "messages": [],
            "block_reason": "",
            "permission_override": None,
        }

        if not self._check_workspace_trust():
            return result

        for hook_def in self.hooks.get(event, []):
            if not isinstance(hook_def, dict):
                continue

            # Check matcher (tool name filter for PreToolUse/PostToolUse)
            matcher = hook_def.get("matcher")
            if matcher and context:
                tool_name = context.get("tool_name", "")
                if matcher != "*" and matcher != tool_name:
                    continue

            command = hook_def.get("command", "")
            if not command:
                continue

            env = self._build_env(event, context)

            try:
                r = subprocess.run(
                    command,
                    shell=True,
                    cwd=self._workdir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=HOOK_TIMEOUT,
                )
                if r.returncode == 0:
                    self._print_hook_output(event, "", r.stdout)
                    self._print_hook_output(event, "stderr: ", r.stderr)
                    try:
                        hook_output = json.loads(r.stdout)
                        if "updatedInput" in hook_output and context:
                            context["tool_input"] = hook_output["updatedInput"]
                        if "additionalContext" in hook_output:
                            result["messages"].append(hook_output["additionalContext"])
                        if "permissionDecision" in hook_output:
                            result["permission_override"] = hook_output["permissionDecision"]
                    except (json.JSONDecodeError, TypeError):
                        pass  # stdout was not JSON -- normal for simple hooks
                elif r.returncode == 1:
                    result["blocked"] = True
                    reason = r.stderr.strip() or "Blocked by hook"
                    result["block_reason"] = reason
                    print(f"  [hook:{event}] BLOCKED: {reason[:HOOK_DISPLAY_LIMIT]}", flush=True)
                elif r.returncode == 2:
                    msg = r.stderr.strip()
                    if msg:
                        result["messages"].append(msg)
                        print(f"  [hook:{event}] INJECT: {msg[:HOOK_DISPLAY_LIMIT]}", flush=True)
            except subprocess.TimeoutExpired:
                print(f"  [hook:{event}] Timeout ({HOOK_TIMEOUT}s)", flush=True)
            except Exception as exc:
                print(f"  [hook:{event}] Error: {exc}", flush=True)

        return result
