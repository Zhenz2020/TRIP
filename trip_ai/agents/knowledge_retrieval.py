from __future__ import annotations

import json
from dataclasses import dataclass

from ..department_playbook import DEPARTMENT_PLAYBOOK
from .core import AgentTrace, GlobalContext, Skill, SkillMetadata


KNOWLEDGE_RETRIEVAL_SKILL = Skill(
    metadata=SkillMetadata(
        name="knowledge-retrieval",
        description="为研判与派单准备可复用知识：部门职责模板、输出硬约束、字段口径；并压缩为短上下文节省 token。",
        inputs=["event_text", "incident_extract_draft"],
        outputs=["playbook_compact", "constraints_compact"],
    ),
    action_guide=(
        "步骤：\n"
        "1) 选择适用的部门职责模板（默认使用内置 playbook）。\n"
        "2) 提取硬约束为短清单（<=1200字），放入 global context，供后续智能体复用。\n"
        "3) 不做推理，不改事实，仅做知识准备与压缩。"
    ),
    resources={"playbook": "trip_ai.department_playbook.DEPARTMENT_PLAYBOOK"},
)


def _compact_playbook(playbook: str) -> tuple[str, str]:
    # Token-friendly compact form: keep department list + hard constraints only.
    lines = [ln.strip() for ln in playbook.splitlines() if ln.strip()]
    dept_lines = []
    constraint_lines = []
    in_constraints = False
    for ln in lines:
        if ln.startswith("通用硬约束"):
            in_constraints = True
            continue
        if not in_constraints and (ln[0].isdigit() and ln.endswith(")")):
            dept_lines.append(ln)
        if in_constraints:
            if ln.startswith("-"):
                constraint_lines.append(ln)
    return "\n".join(dept_lines).strip(), "\n".join(constraint_lines).strip()


@dataclass(frozen=True)
class KnowledgeRetrievalAgent:
    name: str = "知识调取"
    skill: Skill = KNOWLEDGE_RETRIEVAL_SKILL

    def run(self, *, ctx: GlobalContext) -> GlobalContext:
        ctx_skill = (ctx.working_memory.get("skills_override") or {}).get("knowledge-retrieval")
        skill = ctx_skill or self.skill
        pb = DEPARTMENT_PLAYBOOK
        pb_depts, pb_constraints = _compact_playbook(pb)
        ctx.working_memory["playbook_full"] = pb
        ctx.working_memory["playbook_compact"] = pb_depts
        ctx.working_memory["constraints_compact"] = pb_constraints

        ctx.traces.append(
            AgentTrace(
                agent_name=self.name,
                skill_name=skill.metadata.name,
                input_summary="use=DEPARTMENT_PLAYBOOK",
                output_summary=json.dumps(
                    {"depts_len": len(pb_depts), "constraints_len": len(pb_constraints)}, ensure_ascii=False
                ),
                raw_model_output=None,
                resources_used=["playbook"],
            )
        )
        return ctx
