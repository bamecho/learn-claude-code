import tempfile
from pathlib import Path
from src.tools.skill_registry import SkillRegistry, SkillManifest


def test_scan_directory_parses_frontmatter():
    with tempfile.TemporaryDirectory() as td:
        skill_dir = Path(td) / "brainstorming"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: brainstorming\n"
            "description: Brainstorming Ideas Into Designs\n"
            "---\n"
            "\n"
            "# Brainstorming\n\n"
            "Start by understanding the current project context...\n"
        )
        registry = SkillRegistry(skills_dir=td)
        manifests = registry.list_manifests()
        assert len(manifests) == 1
        assert manifests[0].name == "brainstorming"
        assert manifests[0].description == "Brainstorming Ideas Into Designs"
        doc = registry.get("brainstorming")
        assert doc is not None
        assert doc.body.strip() == "# Brainstorming\n\nStart by understanding the current project context..."


def test_missing_frontmatter_skipped(capsys):
    with tempfile.TemporaryDirectory() as td:
        skill_dir = Path(td) / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# No frontmatter here\n")
        registry = SkillRegistry(skills_dir=td)
        assert registry.list_manifests() == []
        assert registry.get("bad-skill") is None
        captured = capsys.readouterr()
        assert "[warning] Skill 'bad-skill': missing or invalid frontmatter, skipping." in captured.out


def test_missing_required_fields_skipped(capsys):
    with tempfile.TemporaryDirectory() as td:
        skill_dir = Path(td) / "incomplete"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: incomplete\n"
            "---\n"
            "\n"
            "body\n"
        )
        registry = SkillRegistry(skills_dir=td)
        assert registry.list_manifests() == []
        assert registry.get("incomplete") is None
        captured = capsys.readouterr()
        assert "[warning] Skill 'incomplete': missing or invalid frontmatter, skipping." in captured.out


def test_nonexistent_directory_returns_empty():
    registry = SkillRegistry(skills_dir="/tmp/nonexistent_skills_dir_xyz")
    assert registry.list_manifests() == []
    assert registry.get("anything") is None


def test_duplicate_skill_name_skipped(capsys):
    with tempfile.TemporaryDirectory() as td:
        first_dir = Path(td) / "first"
        first_dir.mkdir()
        (first_dir / "SKILL.md").write_text(
            "---\n"
            "name: duplicate\n"
            "description: First description\n"
            "---\n"
            "First body\n"
        )
        second_dir = Path(td) / "second"
        second_dir.mkdir()
        (second_dir / "SKILL.md").write_text(
            "---\n"
            "name: duplicate\n"
            "description: Second description\n"
            "---\n"
            "Second body\n"
        )
        registry = SkillRegistry(skills_dir=td)
        manifests = registry.list_manifests()
        assert len(manifests) == 1
        assert manifests[0].name == "duplicate"
        doc = registry.get("duplicate")
        assert doc is not None
        captured = capsys.readouterr()
        assert "[warning] Duplicate skill name 'duplicate' in" in captured.out


def test_quoted_frontmatter_values_parsed():
    with tempfile.TemporaryDirectory() as td:
        skill_dir = Path(td) / "quoted"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            'name: "brainstorming"\n'
            "description: 'Brainstorming Ideas'\n"
            "---\n"
            "\n"
            "Body\n"
        )
        registry = SkillRegistry(skills_dir=td)
        manifests = registry.list_manifests()
        assert len(manifests) == 1
        assert manifests[0].name == "brainstorming"
        assert manifests[0].description == "Brainstorming Ideas"


def test_nested_directory_scanned():
    with tempfile.TemporaryDirectory() as td:
        skill_dir = Path(td) / "deep" / "nested"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: nested-skill\n"
            "description: A deeply nested skill\n"
            "---\n"
            "\n"
            "Nested body\n"
        )
        registry = SkillRegistry(skills_dir=td)
        manifests = registry.list_manifests()
        assert len(manifests) == 1
        assert manifests[0].name == "nested-skill"
        assert manifests[0].description == "A deeply nested skill"
        doc = registry.get("nested-skill")
        assert doc is not None
        assert doc.body.strip() == "Nested body"
