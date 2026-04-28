from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Literal

from src.permissions.constants import READ_ONLY_TOOLS, WRITE_TOOLS
from src.permissions.validator import BashSecurityValidator

_bash_validator = BashSecurityValidator()


@dataclass(frozen=True)
class PermissionRule:
    tool: str
    behavior: Literal["allow", "deny", "ask"]
    path: str | None = None
    content: str | None = None


def _matches(rule: PermissionRule, tool_name: str, tool_input: dict) -> bool:
    if rule.tool != "*" and not fnmatch(tool_name, rule.tool):
        return False
    if rule.path is not None and rule.path != "*":
        target_path = tool_input.get("filePath") or tool_input.get("path", "")
        if not fnmatch(str(target_path), rule.path):
            return False
    if rule.content is not None and rule.content != "*":
        target_content = tool_input.get("command") or tool_input.get("content") or tool_input.get("newText") or ""
        if not fnmatch(str(target_content), rule.content):
            return False
    return True


class PermissionEngine:
    def __init__(
        self,
        mode: Literal["default", "plan", "auto"] = "default",
        rules: list[PermissionRule] | None = None,
    ):
        if mode not in ("default", "plan", "auto"):
            raise ValueError(f"Unknown mode: {mode}")
        self.mode = mode
        self.rules = list(rules) if rules is not None else []
        self.consecutive_denials = 0
        self.max_consecutive_denials = 3

    def add_allow_rule(self, tool: str, path: str = "*") -> None:
        self.rules.append(PermissionRule(tool=tool, behavior="allow", path=path))
        self.consecutive_denials = 0

    def record_denial(self) -> None:
        self.consecutive_denials += 1

    def check(self, tool_name: str, tool_input: dict) -> dict:
        # Step 0: Bash security validation
        if tool_name == "bash":
            command = tool_input.get("command", "")
            failures = _bash_validator.validate(command)
            if failures:
                severe = {"sudo", "rm_rf"}
                severe_hits = [f for f in failures if f[0] in severe]
                if severe_hits:
                    desc = _bash_validator.describe_failures(command)
                    return {"behavior": "deny", "reason": f"Bash validator: {desc}"}
                desc = _bash_validator.describe_failures(command)
                return {"behavior": "ask", "reason": f"Bash validator flagged: {desc}"}

        deny_rules = [r for r in self.rules if r.behavior == "deny"]
        allow_rules = [r for r in self.rules if r.behavior == "allow"]
        ask_rules = [r for r in self.rules if r.behavior == "ask"]

        # 1. deny rules
        for rule in deny_rules:
            if _matches(rule, tool_name, tool_input):
                return {"behavior": "deny", "reason": f"matched deny rule for {rule.tool}"}

        # 2. allow rules
        for rule in allow_rules:
            if _matches(rule, tool_name, tool_input):
                return {"behavior": "allow", "reason": f"matched allow rule for {rule.tool}"}

        # 3. ask rules
        for rule in ask_rules:
            if _matches(rule, tool_name, tool_input):
                return {"behavior": "ask", "reason": f"matched ask rule for {rule.tool}"}

        # 4. mode checks
        if self.mode == "plan":
            if tool_name in WRITE_TOOLS:
                return {"behavior": "deny", "reason": "plan mode blocks writes"}
            return {"behavior": "allow", "reason": "plan mode: read-only allowed"}
        if self.mode == "auto" and tool_name in READ_ONLY_TOOLS:
            return {"behavior": "allow", "reason": "auto mode allows reads"}

        # 5. fallback
        return {"behavior": "ask", "reason": "needs confirmation"}
