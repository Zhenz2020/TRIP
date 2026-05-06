from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class SkillMetadata:
    """
    Tiny, stable summary used as 'global context' to save tokens.
    """

    name: str
    description: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Skill:
    metadata: SkillMetadata
    action_guide: str
    resources: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentTrace:
    agent_name: str
    skill_name: str
    input_summary: str
    output_summary: str
    raw_model_output: str | None = None
    resources_used: list[str] = field(default_factory=list)


@dataclass
class GlobalContext:
    """
    Shared context across agents.
    - metadata_catalog: short descriptions for each agent/skill (token saver)
    - working_memory: structured artifacts passed between agents
    """

    metadata_catalog: list[SkillMetadata] = field(default_factory=list)
    working_memory: dict[str, Any] = field(default_factory=dict)
    traces: list[AgentTrace] = field(default_factory=list)


class Agent(Protocol):
    name: str
    skill: Skill

    def run(self, *, ctx: GlobalContext) -> GlobalContext: ...


def add_metadata(ctx: GlobalContext, *skills: Skill) -> None:
    for s in skills:
        ctx.metadata_catalog.append(s.metadata)

