import tempfile
from pathlib import Path
from src.tools.skill_tool import SkillTool
from src.tools.skill_registry import SkillRegistry
from src.tools.base import ToolResult


def test_load_existing_skill():
    with tempfile.TemporaryDirectory() as td:
        skill_dir = Path(td) / "code-review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: code-review\n"
            "description: Checklist for reviewing code changes\n"
            "---\n"
            "\n"
            "1. Check for tests\n"
        )
        registry = SkillRegistry(skills_dir=td)
        tool = SkillTool(registry)
        result = tool.execute("tu-1", {"name": "code-review"})
        assert not result.is_error
        assert result.content.strip() == "1. Check for tests"


def test_empty_name_returns_error():
    registry = SkillRegistry(skills_dir="/tmp/nonexistent_xyz")
    tool = SkillTool(registry)
    result = tool.execute("tu-2", {"name": ""})
    assert result.is_error
    assert "Missing" in result.content


def test_missing_name_returns_error():
    registry = SkillRegistry(skills_dir="/tmp/nonexistent_xyz")
    tool = SkillTool(registry)
    result = tool.execute("tu-3", {})
    assert result.is_error
    assert "Missing" in result.content


def test_unknown_name_returns_error_with_list():
    with tempfile.TemporaryDirectory() as td:
        skill_dir = Path(td) / "brainstorming"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: brainstorming\n"
            "description: Brainstorm ideas\n"
            "---\n"
            "\n"
            "body\n"
        )
        registry = SkillRegistry(skills_dir=td)
        tool = SkillTool(registry)
        result = tool.execute("tu-4", {"name": "nonexistent"})
        assert result.is_error
        assert "brainstorming" in result.content
