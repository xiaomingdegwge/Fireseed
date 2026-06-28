from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class Skill:
    # Skill 是一段可复用提示词。slash command 触发后，会把它变成下一轮模型输入。
    name: str
    description: str = ""
    when_to_use: str = ""
    user_invocable: bool = True
    argument_hint: str = ""
    source: str = "project"
    skill_root: str | None = None
    _prompt_text: str = ""
    _prompt_fn: Callable[[str], str] | None = None

    def get_prompt(self, args: str = "") -> str:
        if self._prompt_fn is not None:
            return self._prompt_fn(args)
        text = self._prompt_text.replace("$ARGUMENTS", args)
        if self.skill_root:
            text = text.replace("${CLAUDE_SKILL_DIR}", self.skill_root)
        if args and self.argument_hint:
            text = text.replace(f"${{{self.argument_hint}}}", args)
        return text


_REGISTRY: dict[str, Skill] = {}
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def register_skill(skill: Skill) -> None:
    _REGISTRY[skill.name] = skill


def get_skill(name: str) -> Skill | None:
    return _REGISTRY.get(name)


def list_skills(user_invocable_only: bool = True) -> list[Skill]:
    skills = list(_REGISTRY.values())
    if user_invocable_only:
        skills = [skill for skill in skills if skill.user_invocable]
    return sorted(skills, key=lambda skill: (skill.source != "bundled", skill.name))


def clear_skills(source: str | None = None) -> None:
    if source is None:
        _REGISTRY.clear()
        return
    for name, skill in list(_REGISTRY.items()):
        if skill.source == source:
            del _REGISTRY[name]


def load_skills_from_dir(skills_dir: Path, source: str = "project") -> list[Skill]:
    loaded: list[Skill] = []
    if not skills_dir.is_dir():
        return loaded

    for entry in sorted(skills_dir.iterdir()):
        skill_path: Path | None = None
        skill_root: Path
        if entry.is_dir():
            skill_path = entry / "SKILL.md"
            skill_root = entry
        elif entry.suffix == ".md":
            skill_path = entry
            skill_root = entry.parent
        else:
            continue

        if not skill_path.exists():
            continue
        try:
            text = skill_path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = _parse_frontmatter(text)
        skill = _skill_from_meta(meta, body, name=entry.stem, source=source, skill_root=str(skill_root))
        if skill._prompt_text:
            register_skill(skill)
            loaded.append(skill)
    return loaded


def discover_skills(cwd: str | None = None) -> list[Skill]:
    loaded: list[Skill] = []
    loaded.extend(load_skills_from_dir(Path.home() / ".fireseed" / "skills", source="user"))
    if cwd:
        loaded.extend(load_skills_from_dir(Path(cwd) / ".fireseed" / "skills", source="project"))
    return loaded


def build_skills_prompt_section() -> str:
    skills = list_skills(user_invocable_only=False)
    if not skills:
        return ""
    lines = ["", "# Available Skills"]
    for skill in skills:
        line = f"- /{skill.name}: {skill.description or '(no description)'}"
        if skill.when_to_use:
            line += f" — {skill.when_to_use}"
        lines.append(line)
    return "\n".join(lines)


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, Any] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower().replace("-", "_")] = _parse_value(value.strip())
    return meta, text[match.end():]


def _parse_value(value: str) -> Any:
    if value.lower() in {"true", "yes"}:
        return True
    if value.lower() in {"false", "no"}:
        return False
    if "," in value:
        return [part.strip() for part in value.split(",") if part.strip()]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _skill_from_meta(meta: dict[str, Any], body: str, *, name: str, source: str, skill_root: str) -> Skill:
    return Skill(
        name=str(meta.get("name") or name),
        description=str(meta.get("description") or ""),
        when_to_use=str(meta.get("when_to_use") or ""),
        user_invocable=bool(meta.get("user_invocable", True)),
        argument_hint=str(meta.get("arguments") or ""),
        source=source,
        skill_root=skill_root,
        _prompt_text=body.strip(),
    )
