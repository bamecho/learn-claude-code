import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillManifest:
    name: str
    description: str


@dataclass(frozen=True)
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
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            skill_file = entry / "SKILL.md"
            if not skill_file.exists():
                continue
            parsed = self._parse_file(skill_file.read_text(encoding="utf-8"))
            if parsed is None:
                continue
            manifest, body = parsed
            if not manifest.name or not manifest.description:
                print(f"[warning] Skill '{entry.name}' missing required frontmatter fields, skipping.")
                continue
            self._skills[manifest.name] = SkillDocument(manifest=manifest, body=body)

    def _parse_file(self, text: str) -> tuple[SkillManifest, str] | None:
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
            data[key.strip()] = value.strip()
        name = data.get("name", "")
        description = data.get("description", "")
        if not name or not description:
            return None
        return SkillManifest(name=name, description=description), body

    def list_manifests(self) -> list[SkillManifest]:
        return [doc.manifest for doc in self._skills.values()]

    def get(self, name: str) -> SkillDocument | None:
        return self._skills.get(name)
