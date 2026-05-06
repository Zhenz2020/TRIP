from __future__ import annotations

import json
from dataclasses import dataclass

from ..department_playbook import DEPARTMENT_PLAYBOOK
from ..llm_siliconflow import ChatMessage, SiliconFlowClient
from ..normalize import normalize_risk_assessment_payload
from ..schemas import IncidentExtract, RiskAssessment, RiskLevel
from ..pipeline import _extract_json, _repair_to_valid_json
from .core import AgentTrace, GlobalContext, Skill, SkillMetadata


PLAN_GENERATION_SKILL = Skill(
    metadata=SkillMetadata(
        name="plan-generation",
        description="把风险研判转成按部门分发的可执行任务清单（含channel/target/eta/priority）。",
        inputs=["event_text", "incident_extract_draft", "risk_assessment_partial", "playbook_full"],
        outputs=["risk_assessment_with_actions"],
    ),
    action_guide=(
        "步骤：\n"
        "1) 读取风险研判结果与结构化要素。\n"
        "2) 严格遵循部门职责模板输出 suggested_actions（跨部门、可执行、参数化）。\n"
        "3) 严格 JSON 输出，解析失败则进行一次 JSON 修复。"
    ),
    resources={"llm": "SiliconFlow chat.completions", "playbook": "DEPARTMENT_PLAYBOOK"},
)


@dataclass(frozen=True)
class PlanGenerationAgent:
    name: str = "方案生成"
    skill: Skill = PLAN_GENERATION_SKILL

    def run(self, *, ctx: GlobalContext) -> GlobalContext:
        ctx_skill = (ctx.working_memory.get("skills_override") or {}).get("plan-generation")
        skill = ctx_skill or self.skill
        client: SiliconFlowClient = ctx.working_memory["llm_client"]
        text: str = ctx.working_memory["event_text"]
        extract: IncidentExtract = ctx.working_memory["incident_extract_draft"]
        partial: RiskAssessment = ctx.working_memory["risk_assessment_partial"]
        playbook: str = ctx.working_memory.get("playbook_full") or DEPARTMENT_PLAYBOOK

        schema_hint = RiskAssessment.model_json_schema()
        prompt = (
            "你是高速事故处置方案生成助手。目标：输出按部门分发的可执行任务清单。\n"
            "严格只输出 JSON 本体，必须可被 json.loads 解析（null小写、双引号、无尾逗号）。\n"
            "必须遵循部门职责模板（playbook）与通用硬约束。\n\n"
            f"部门职责模板（playbook）：\n{playbook}\n\n"
            f"JSON Schema：\n{json.dumps(schema_hint, ensure_ascii=False)}\n\n"
            f"原文：\n{text}\n\n"
            f"结构化要素：\n{json.dumps(extract.model_dump(), ensure_ascii=False)}\n\n"
            f"风险研判（不含措施或仅部分）：\n{json.dumps(partial.model_dump(), ensure_ascii=False)}\n\n"
            "输出要求：\n"
            "- suggested_actions 必须覆盖至少 3 个不同 department；每个 department 至少 2 条\n"
            "- 每条措施必须包含：department、action、priority、channel、target、eta_minutes、rationale\n"
            "- 禁止复述原文整句，必须任务化/参数化表达\n"
        )
        messages = [ChatMessage(role="user", content=prompt)]
        raw_text = client.chat_completions(messages=messages, max_tokens=900, temperature=0.7)

        raw = None
        assessment = None
        try:
            raw = normalize_risk_assessment_payload(_extract_json(raw_text))
            assessment = RiskAssessment.model_validate(raw)
        except Exception as e1:  # noqa: BLE001
            repaired = _repair_to_valid_json(client, schema_hint=schema_hint, bad_text=raw_text)
            try:
                raw = normalize_risk_assessment_payload(_extract_json(repaired))
                assessment = RiskAssessment.model_validate(raw)
            except Exception as e2:  # noqa: BLE001
                # Strict mode: bubble up so caller can notice immediately.
                raise RuntimeError(
                    "Plan generation LLM output invalid after repair. "
                    f"first_error={e1}; repair_error={e2}; raw_text={raw_text[:500]!r}"
                ) from e2

        ctx.working_memory["risk_assessment_with_actions"] = assessment
        ctx.working_memory["raw_llm_plan_text"] = raw_text
        ctx.working_memory["raw_llm_plan_json"] = raw

        ctx.traces.append(
            AgentTrace(
                agent_name=self.name,
                skill_name=skill.metadata.name,
                input_summary=f"risk_level={partial.risk_level}",
                output_summary=json.dumps({"actions": len(assessment.suggested_actions)}, ensure_ascii=False),
                raw_model_output=raw_text,
                resources_used=["llm", "playbook"],
            )
        )
        return ctx
