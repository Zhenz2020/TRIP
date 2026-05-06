from __future__ import annotations

import json
from dataclasses import dataclass

from ..llm_siliconflow import SiliconFlowClient
from ..schemas import IncidentExtract
from ..pipeline import llm_extract_incident
from ..resources.ocr_tool import OcrTool
from .core import AgentTrace, GlobalContext, Skill, SkillMetadata


EVENT_UNDERSTANDING_SKILL = Skill(
    metadata=SkillMetadata(
        name="event-understanding",
        description="从图片/PDF/文本中理解事故工单：OCR/视觉理解→得到可用于下游推理的干净文本与关键要素。",
        inputs=["uploaded_file(bytes,mime,filename) | text"],
        outputs=["event_text", "ocr_markdown", "ocr_plain_text", "incident_extract(draft)"],
    ),
    action_guide=(
        "步骤：\n"
        "1) 若有上传图片/PDF：优先调用 OCR 工具抽取 plain_text 与 markdown，并记录 raw。\n"
        "2) 可选：若是图片且 OCR 质量差，调用视觉模型做补充理解（只产出补充文本，不要复述）。\n"
        "3) 产出 event_text：用于下游智能体的主文本。\n"
        "4) 用文本模型做一次 IncidentExtract 草稿抽取（严格 JSON），为后续风险研判提供结构化输入。\n"
        "5) 保存 trace（原始模型输出/资源调用）。"
    ),
    resources={"ocr_tool": "trip_ai.resources.ocr_tool.OcrTool", "vision_model": "SiliconFlow vision"},
)


@dataclass(frozen=True)
class EventUnderstandingAgent:
    name: str = "事件理解"
    skill: Skill = EVENT_UNDERSTANDING_SKILL

    def run(self, *, ctx: GlobalContext) -> GlobalContext:
        # Hot-plug skill override (UI/config).
        ctx_skill = (ctx.working_memory.get("skills_override") or {}).get("event-understanding")
        skill = ctx_skill or self.skill
        settings = ctx.working_memory["settings"]
        client: SiliconFlowClient = ctx.working_memory["llm_client"]
        uploaded_files = ctx.working_memory.get("uploaded_files")
        uploaded = ctx.working_memory.get("uploaded_file")  # backward compat
        user_text = (ctx.working_memory.get("input_text") or "").strip()
        text = user_text

        resources_used: list[str] = []
        ocr_markdowns: list[str] = []
        ocr_plains: list[str] = []
        ocr_raws: list[dict] = []

        # 1) OCR tool (resource)
        if not uploaded_files and uploaded:
            uploaded_files = [uploaded]

        if uploaded_files:
            ocr_tool = OcrTool(settings=settings)
            base_parts: list[str] = []
            for f in uploaded_files:
                if not (f and f.get("bytes") and f.get("filename")):
                    continue
                parsed = ocr_tool.run(file_bytes=f["bytes"], filename=f["filename"])
                resources_used.append("ocr_tool")
                if parsed.markdown:
                    ocr_markdowns.append(parsed.markdown)
                if parsed.plain_text:
                    ocr_plains.append(parsed.plain_text)
                if parsed.raw:
                    ocr_raws.append(parsed.raw)

                base = parsed.plain_text or parsed.markdown or ""
                if base:
                    base_parts.append(f"[{f.get('filename')}]")
                    base_parts.append(base.strip())

            base_text = "\n\n---\n\n".join(base_parts).strip()
            if base_text and user_text:
                text = base_text + "\n\n[用户补充]\n" + user_text
            elif base_text:
                text = base_text
            else:
                text = user_text

        # 2) Optional vision understanding (resource)
        # Only when image and OCR text seems too short.
        raw_vision = None
        # For multi-image, only attempt vision on the first image when OCR is too short.
        first_img = None
        if uploaded_files:
            for f in uploaded_files:
                if (f.get("mime") or "").startswith("image/") and f.get("bytes"):
                    first_img = f
                    break
        elif uploaded and (uploaded.get("mime") or "").startswith("image/"):
            first_img = uploaded

        if first_img and len(text) < 40:
            try:
                prompt = (
                    "你是高速事故工单图片理解助手。请阅读图片内容，输出用于后续研判的“干净文本”。"
                    "要求：不要输出Markdown，不要解释，只输出文本；尽量补全位置/方向/车道/事件类型/伤亡/危化等关键信息。"
                )
                raw_vision = client.vision_understand(
                    prompt=prompt, image_bytes=first_img["bytes"], mime_type=first_img.get("mime") or "image/png"
                )
                resources_used.append("vision_model")
                # Use vision text as fallback/augmentation. Preserve user supplement if present.
                v = (raw_vision or "").strip()
                if v:
                    if user_text:
                        v = v + "\n\n[用户补充]\n" + user_text
                    if len(v) > len(text.strip()):
                        text = v
            except Exception as e:  # noqa: BLE001
                raw_vision = f"[vision_failed] {e}"

        # 3) Draft extraction
        extract = IncidentExtract(confidence=0.1, evidence=[])
        raw_extract = None
        raw_extract_text = None
        has_uploads = bool(uploaded_files) or bool(uploaded)
        input_summary = f"uploaded={has_uploads} text_len={len(text)}"
        try:
            extract, raw_extract, raw_extract_text = llm_extract_incident(client, text)
        except Exception as e:  # noqa: BLE001
            extract = IncidentExtract(confidence=0.1, evidence=[f"事件理解抽取失败：{e}"])
            raw_extract = {"error": str(e)}
            # Make the failure visible in traces/UI; avoid silent None.
            raw_extract_text = f"[event_understanding_extract_failed] {e}"

        ctx.working_memory.update(
            {
                "event_text": text,
                "ocr_markdown": "\n\n---\n\n".join(ocr_markdowns).strip() if ocr_markdowns else None,
                "ocr_plain_text": "\n\n---\n\n".join(ocr_plains).strip() if ocr_plains else None,
                "ocr_raw": ocr_raws if ocr_raws else None,
                "vision_text": raw_vision,
                "incident_extract_draft": extract,
                "raw_llm_extract": raw_extract,
                "raw_llm_extract_text": raw_extract_text,
            }
        )

        out_summary = json.dumps(
            {
                "event_text_len": len(text),
                "extract_conf": extract.confidence,
                "resources_used": resources_used,
            },
            ensure_ascii=False,
        )
        ctx.traces.append(
            AgentTrace(
                agent_name=self.name,
                skill_name=skill.metadata.name,
                input_summary=input_summary,
                output_summary=out_summary,
                raw_model_output=raw_extract_text,
                resources_used=resources_used,
            )
        )
        return ctx
