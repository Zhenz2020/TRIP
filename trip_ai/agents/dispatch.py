from __future__ import annotations

import json
from dataclasses import dataclass

from ..schemas import RiskAssessment
from .core import AgentTrace, GlobalContext, Skill, SkillMetadata


DISPATCH_SKILL = Skill(
    metadata=SkillMetadata(
        name="dispatch",
        description="把分部门任务清单整理为可下发的 payload（目前仅生成草稿，不做真实外部对接）。",
        inputs=["risk_assessment_with_actions"],
        outputs=["dispatch_payloads"],
    ),
    action_guide=(
        "步骤：\n"
        "1) 按 department 分组 suggested_actions。\n"
        "2) 为每个部门生成一个 dispatch_payload（包含任务列表、优先级、目标范围）。\n"
        "3) 不调用外部系统，只产出可供对接的结构。"
    ),
    resources={},
)


@dataclass(frozen=True)
class DispatchAgent:
    name: str = "决策下发"
    skill: Skill = DISPATCH_SKILL

    def run(self, *, ctx: GlobalContext) -> GlobalContext:
        ctx_skill = (ctx.working_memory.get("skills_override") or {}).get("dispatch")
        skill = ctx_skill or self.skill
        assessment: RiskAssessment = ctx.working_memory["risk_assessment_with_actions"]
        items = [a.model_dump() for a in (assessment.suggested_actions or [])]
        by_dept: dict[str, list[dict]] = {}
        for a in items:
            by_dept.setdefault(a.get("department") or "未分配", []).append(a)

        payloads = []
        for dept, actions in by_dept.items():
            actions_sorted = sorted(actions, key=lambda x: int(x.get("priority") or 3))
            payloads.append(
                {
                    "department": dept,
                    "risk_level": assessment.risk_level,
                    "tasks": actions_sorted,
                }
            )

        ctx.working_memory["dispatch_payloads"] = payloads
        ctx.traces.append(
            AgentTrace(
                agent_name=self.name,
                skill_name=skill.metadata.name,
                input_summary=f"actions={len(items)}",
                output_summary=json.dumps({"departments": len(by_dept)}, ensure_ascii=False),
                raw_model_output=None,
                resources_used=[],
            )
        )
        return ctx
