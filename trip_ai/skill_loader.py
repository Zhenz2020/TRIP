from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .agents.core import Skill, SkillMetadata


def _parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """
    Very small YAML-frontmatter parser supporting simple scalars/lists/dicts.
    We intentionally keep it minimal to avoid extra deps (PyYAML).
    """
    s = text.lstrip()
    if not s.startswith("---"):
        return {}, text
    parts = s.split("\n")
    # find second --- line
    end_idx = None
    for i in range(1, len(parts)):
        if parts[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, text
    fm_lines = parts[1:end_idx]
    body = "\n".join(parts[end_idx + 1 :]).lstrip("\n")

    def parse_value(v: str) -> Any:
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            if not inner:
                return []
            return [x.strip().strip("'\"") for x in inner.split(",")]
        if v in ("[]", "{}"):
            return [] if v == "[]" else {}
        return v.strip().strip("'\"")

    data: dict[str, Any] = {}
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, rest = line.split(":", 1)
        key = key.strip()
        rest = rest.rstrip()
        if rest.strip() == "":
            # parse indented block list:
            j = i + 1
            items: list[Any] = []
            obj: dict[str, Any] = {}
            mode = None
            while j < len(fm_lines) and (fm_lines[j].startswith("  ") or fm_lines[j].startswith("\t")):
                ln = fm_lines[j].lstrip()
                if ln.startswith("- "):
                    mode = "list"
                    items.append(ln[2:].strip().strip("'\""))
                elif ":" in ln:
                    mode = "dict"
                    k2, v2 = ln.split(":", 1)
                    obj[k2.strip()] = parse_value(v2)
                j += 1
            data[key] = items if mode == "list" else obj
            i = j
            continue
        data[key] = parse_value(rest)
        i += 1

    return data, body


def load_skills(skills_dir: str | os.PathLike = "skills") -> list[Skill]:
    skills_path = Path(skills_dir)
    if not skills_path.exists():
        return []

    out: list[Skill] = []
    for p in sorted(skills_path.glob("*.md")):
        if p.name.lower() == "readme.md":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fm, body = _parse_front_matter(text)
        meta = SkillMetadata(
            name=str(fm.get("name") or p.stem),
            description=str(fm.get("description") or ""),
            inputs=list(fm.get("inputs") or []),
            outputs=list(fm.get("outputs") or []),
        )
        # Store agent name and file path into resources for discoverability.
        resources = {
            "agent": str(fm.get("agent") or ""),
            "file": str(p.as_posix()),
            "resources": fm.get("resources") or [],
        }
        skill = Skill(metadata=meta, action_guide=body.strip(), resources=resources)
        out.append(skill)
    return out


def skills_by_agent(skills: list[Skill]) -> dict[str, list[Skill]]:
    out: dict[str, list[Skill]] = {}
    for s in skills:
        agent = str((s.resources or {}).get("agent") or "").strip()
        if not agent:
            continue
        out.setdefault(agent, []).append(s)
    return out


def skill_to_dict(skill: Skill) -> dict[str, Any]:
    return {
        "metadata": asdict(skill.metadata),
        "action_guide": skill.action_guide,
        "resources": skill.resources,
    }

