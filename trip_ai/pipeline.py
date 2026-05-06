from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from .department_playbook import DEPARTMENT_PLAYBOOK
from .llm_siliconflow import ChatMessage, SiliconFlowClient
from .schemas import IncidentExtract, PipelineResult, RiskAssessment, RiskLevel


def _extract_json(text: str) -> dict[str, Any]:
    """
    Best-effort JSON extractor for models that wrap JSON with prose/fences.
    """
    s = text.strip()
    if "```" in s:
        # take the largest fenced block
        parts = s.split("```")
        s = max(parts, key=len).strip()
        if s.startswith("json"):
            s = s[4:].strip()
    # find first '{'...' }'
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        s = s[start : end + 1]

    def _sanitize_json_like(t: str) -> str:
        # Replace common non-JSON nulls.
        t = re.sub(r"\bNULL\b", "null", t)
        t = re.sub(r"\bNone\b", "null", t)
        # Remove trailing commas before object/array close.
        t = re.sub(r",\s*([}\]])", r"\1", t)
        return t

    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        s2 = _sanitize_json_like(s)
        obj = json.loads(s2)

    if obj is None:
        # Model sometimes returns literal `null`, which is valid JSON but unusable for our schemas.
        raise ValueError("Model returned JSON null")
    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object, got {type(obj).__name__}")
    return obj


def _repair_to_valid_json(
    client: SiliconFlowClient, *, schema_hint: dict[str, Any], bad_text: str
) -> str:
    """
    One-shot "JSON fixer" prompt: convert model output into strictly valid JSON.
    Keep it minimal and deterministic (low temperature).
    """
    messages = [
        ChatMessage(
            role="system",
            content=(
                "你是 JSON 修复器。你的任务是把输入内容修复为严格合法的 JSON。"
                "必须100%可被 Python 的 json.loads 解析。"
                "只能输出 JSON 本体，禁止任何解释/Markdown/代码块标记。"
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                "请按以下 JSON Schema 修复输出：\n"
                f"{json.dumps(schema_hint, ensure_ascii=False)}\n\n"
                "修复要求：\n"
                "- 只能输出一个 JSON 对象\n"
                "- 使用 null（小写），禁止 NULL/None\n"
                "- 字符串必须用双引号\n"
                "- 不要尾随逗号\n\n"
                "- 必须包含 Schema 所需字段；若为数组元素，也必须包含其必需字段（例如 action/department 等）\n\n"
                f"待修复内容：\n{bad_text}"
            ),
        ),
    ]
    return client.chat_completions(messages=messages, max_tokens=900, temperature=0.0)


def llm_extract_incident(
    client: SiliconFlowClient, text: str
) -> tuple[IncidentExtract, dict[str, Any], str]:
    schema_hint = IncidentExtract.model_json_schema()
    messages = [
        ChatMessage(
            role="system",
            content=(
                "你是高速公路事故工单信息抽取助手。"
                "请从输入文本中抽取事故要素，并严格只输出 JSON（不要输出解释/Markdown）。"
                "输出必须为严格合法 JSON：使用 null（小写），禁止 NULL/None；字符串用双引号；不要尾随逗号。"
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                "请按以下 JSON Schema 输出字段（缺失填 null，证据放到 evidence 列表里，confidence 0-1）：\n"
                f"{json.dumps(schema_hint, ensure_ascii=False)}\n\n"
                f"工单文本：\n{text}"
            ),
        ),
    ]
    out_text = client.chat_completions(messages=messages, max_tokens=700, temperature=0.2)
    try:
        raw = _extract_json(out_text)
        extract = IncidentExtract.model_validate(raw)
    except (json.JSONDecodeError, ValidationError):
        repaired_text = _repair_to_valid_json(client, schema_hint=schema_hint, bad_text=out_text)
        raw = _extract_json(repaired_text)
        raw["_repaired"] = True
        raw["_repaired_text"] = repaired_text
        extract = IncidentExtract.model_validate(raw)
    return extract, raw, out_text


def llm_assess_risk(
    client: SiliconFlowClient, text: str, extract: IncidentExtract
) -> tuple[RiskAssessment, dict[str, Any], str]:
    schema_hint = RiskAssessment.model_json_schema()
    messages = [
        ChatMessage(
            role="system",
            content=(
                "你是高速公路事故应急指挥研判助手。"
                "根据结构化要素进行风险研判与管控建议。"
                "严格只输出 JSON（不要输出解释/Markdown）。"
                "输出必须为严格合法 JSON：使用 null（小写），禁止 NULL/None；字符串用双引号；不要尾随逗号。"
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                "请按以下 JSON Schema 输出（risk_level 只能是 I/II/III/IV/UNKNOWN；"
                " suggested_actions 输出“按部门分发的可执行任务清单”（含 priority 1-5）：\n"
                f"{json.dumps(schema_hint, ensure_ascii=False)}\n\n"
                "以下是部门职责模板（playbook），请严格遵循：\n"
                f"{DEPARTMENT_PLAYBOOK}\n\n"
                f"原文：\n{text}\n\n"
                f"结构化要素：\n{json.dumps(extract.model_dump(), ensure_ascii=False)}"
            ),
        ),
    ]
    out_text = client.chat_completions(messages=messages, max_tokens=700, temperature=0.7)
    try:
        raw = _extract_json(out_text)
        assessment = RiskAssessment.model_validate(raw)
    except (json.JSONDecodeError, ValidationError):
        repaired_text = _repair_to_valid_json(client, schema_hint=schema_hint, bad_text=out_text)
        raw = _extract_json(repaired_text)
        raw["_repaired"] = True
        raw["_repaired_text"] = repaired_text
        assessment = RiskAssessment.model_validate(raw)
    return assessment, raw, out_text


def run_pipeline(*, client: SiliconFlowClient, text: str, ocr_markdown: str | None = None) -> PipelineResult:
    try:
        extract, raw_extract, raw_extract_text = llm_extract_incident(client, text)
    except (ValidationError, json.JSONDecodeError) as e:
        # If extraction fails, degrade gracefully.
        extract = IncidentExtract(confidence=0.1, evidence=[f"LLM抽取失败：{e}"])
        raw_extract = {"error": str(e)}
        raw_extract_text = None

    try:
        assessment, raw_assess, raw_assess_text = llm_assess_risk(client, text, extract)
    except (ValidationError, json.JSONDecodeError) as e:
        assessment = RiskAssessment(
            risk_level=RiskLevel.UNKNOWN,
            confidence=0.1,
            reasons=[f"LLM研判失败：{e}"],
            suggested_actions=[],
        )
        raw_assess = {"error": str(e)}
        raw_assess_text = None

    return PipelineResult(
        input_text=text,
        ocr_markdown=ocr_markdown,
        ocr_plain_text=None,
        ocr_raw=None,
        extract=extract,
        assessment=assessment,
        raw_llm_extract_text=raw_extract_text,
        raw_llm_extract=raw_extract,
        raw_llm_assess_text=raw_assess_text,
        raw_llm_assess=raw_assess,
    )


def run_pipeline_with_ocr(
    *,
    client: SiliconFlowClient,
    input_text: str,
    uploaded_filename: str | None,
    uploaded_mime: str | None,
    ocr_markdown: str | None,
    ocr_plain_text: str | None,
    ocr_raw: dict[str, Any] | None,
) -> PipelineResult:
    res = run_pipeline(client=client, text=input_text, ocr_markdown=ocr_markdown)
    return res.model_copy(
        update={
            "uploaded_filename": uploaded_filename,
            "uploaded_mime": uploaded_mime,
            "ocr_plain_text": ocr_plain_text,
            "ocr_raw": ocr_raw,
        }
    )
