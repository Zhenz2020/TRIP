from __future__ import annotations

import json
from dataclasses import dataclass

from ..llm_siliconflow import ChatMessage, SiliconFlowClient
from ..normalize import normalize_risk_assessment_payload
from ..schemas import IncidentExtract, RiskAssessment, RiskLevel
from ..pipeline import _extract_json, _repair_to_valid_json
from .core import AgentTrace, GlobalContext, Skill, SkillMetadata


RISK_ASSESSMENT_SKILL = Skill(
    metadata=SkillMetadata(
        name="risk-assessment",
        description="基于事件理解产物进行风险研判（分级+原因），不生成具体处置措施。",
        inputs=["event_text", "incident_extract_draft", "constraints_compact"],
        outputs=["risk_assessment_partial"],
    ),
    action_guide=(
        "步骤：\n"
        "1) 输入 event_text 与 incident_extract_draft。\n"
        "2) 输出 RiskAssessment，但 suggested_actions 先留空（由下游方案生成智能体填充）。\n"
        "3) 严格 JSON 输出，解析失败则进行一次 JSON 修复。"
    ),
    resources={"llm": "SiliconFlow chat.completions"},
)


@dataclass(frozen=True)
class RiskAssessmentAgent:
    name: str = "风险研判"
    skill: Skill = RISK_ASSESSMENT_SKILL

    def run(self, *, ctx: GlobalContext) -> GlobalContext:
        ctx_skill = (ctx.working_memory.get("skills_override") or {}).get("risk-assessment")
        skill = ctx_skill or self.skill
        client: SiliconFlowClient = ctx.working_memory["llm_client"]
        text: str = ctx.working_memory["event_text"]
        extract: IncidentExtract = ctx.working_memory["incident_extract_draft"]
        constraints: str = ctx.working_memory.get("constraints_compact") or ""

        schema_hint = RiskAssessment.model_json_schema()
        prompt = (
            "你是高速事故风险研判助手。只做风险分级与原因说明，不要输出具体处置措施。\n"
            "严格只输出 JSON 本体，必须可被 json.loads 解析（null小写、双引号、无尾逗号）。\n"
            "输出时 suggested_actions 必须是空数组 []。\n"
            f"硬约束：\n{constraints}\n\n"
            f"JSON Schema：\n{json.dumps(schema_hint, ensure_ascii=False)}\n\n"
            f"原文：\n{text}\n\n"
            f"结构化要素：\n{json.dumps(extract.model_dump(), ensure_ascii=False)}"
        )
        messages = [ChatMessage(role="user", content=prompt)]

        raw_text = client.chat_completions(messages=messages, max_tokens=700, temperature=0.4)
        raw = None
        assessment = None
        try:
            raw = normalize_risk_assessment_payload(_extract_json(raw_text))
            raw["suggested_actions"] = []
            assessment = RiskAssessment.model_validate(raw)
        except Exception as e1:  # noqa: BLE001
            repaired = _repair_to_valid_json(client, schema_hint=schema_hint, bad_text=raw_text)
            try:
                raw = normalize_risk_assessment_payload(_extract_json(repaired))
                raw["suggested_actions"] = []
                assessment = RiskAssessment.model_validate(raw)
            except Exception as e2:  # noqa: BLE001
                # Strict mode: bubble up so caller can notice immediately.
                raise RuntimeError(
                    "Risk assessment LLM output invalid after repair. "
                    f"first_error={e1}; repair_error={e2}; raw_text={raw_text[:500]!r}"
                ) from e2

        ctx.working_memory["risk_assessment_partial"] = assessment
        ctx.working_memory["raw_llm_risk_text"] = raw_text
        ctx.working_memory["raw_llm_risk_json"] = raw

        ctx.traces.append(
            AgentTrace(
                agent_name=self.name,
                skill_name=skill.metadata.name,
                input_summary=f"text_len={len(text)}",
                output_summary=json.dumps(
                    {"risk_level": assessment.risk_level, "confidence": assessment.confidence}, ensure_ascii=False
                ),
                raw_model_output=raw_text,
                resources_used=["llm"],
            )
        )
        return ctx
