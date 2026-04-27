import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkillManifest:
    name: str
    description: str
    path: Path


@dataclass
class SkillDocument:
    manifest: SkillManifest
    body: str


class SkillRegistry:
    def __init__(self, skills_dir: str):
        self._skills: dict[str, SkillDocument] = {}
        self._scan(Path(skills_dir))

    def _scan(self, root: Path) -> None:
        if not root.exists() or not root.is_dir():
            return
        for skill_file in sorted(root.rglob("SKILL.md")):
            try:
                text = skill_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                print(f"[warning] Skill '{skill_file.parent.name}': failed to read file, skipping.")
                continue
            parsed = self._parse_file(text, skill_file)
            if parsed is None:
                print(f"[warning] Skill '{skill_file.parent.name}': missing or invalid frontmatter, skipping.")
                continue
            manifest, body = parsed
            if manifest.name in self._skills:
                print(f"[warning] Duplicate skill name '{manifest.name}' in '{skill_file.parent.name}', skipping.")
                continue
            self._skills[manifest.name] = SkillDocument(manifest=manifest, body=body)

    def _parse_file(self, text: str, path: Path) -> tuple[SkillManifest, str] | None:
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
        if not match:
            return None
        front = match.group(1)
        body = match.group(2)
        data: dict[str, str] = {}
        for line in front.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            data[key.strip()] = value
        name = data.get("name", "")
        description = data.get("description", "")
        if not name or not description:
            return None
        return SkillManifest(name=name, description=description, path=path), body

    def list_manifests(self) -> list[SkillManifest]:
        return [doc.manifest for doc in self._skills.values()]

    def get(self, name: str) -> SkillDocument | None:
        return self._skills.get(name)
