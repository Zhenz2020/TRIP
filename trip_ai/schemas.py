from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    I = "I"  # 特别重大
    II = "II"
    III = "III"
    IV = "IV"  # 一般
    UNKNOWN = "UNKNOWN"


class IncidentExtract(BaseModel):
    occurred_time: str | None = Field(default=None, description="事故发生时间，无法确定则空")
    road_name: str | None = Field(default=None, description="高速/路段名称，如 G15 沈海高速")
    stake: str | None = Field(default=None, description="桩号，如 K123+456")
    direction: str | None = Field(default=None, description="方向/上下行/往某地方向")
    location_desc: str | None = Field(default=None, description="位置补充描述，如 互通/收费站/隧道/桥梁")

    event_type: str | None = Field(default=None, description="事件类型：追尾/侧翻/自燃/抛洒物/故障车等")
    vehicles_involved: int | None = Field(default=None, description="涉事车辆数量")
    casualties: str | None = Field(default=None, description="伤亡情况描述")
    hazmat: bool | None = Field(default=None, description="是否涉及危化品/危货车")

    lanes_blocked: str | None = Field(default=None, description="占用车道情况，如 第2车道/两车道/主线全封")
    congestion: str | None = Field(default=None, description="拥堵/缓行描述，如 2km 拥堵")
    weather: str | None = Field(default=None, description="天气/能见度")

    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="抽取置信度")
    evidence: list[str] = Field(default_factory=list, description="关键证据原文片段")


class ControlAction(BaseModel):
    department: str = Field(
        description=(
            "责任部门/业务方，例如：诱导大屏、路面处置、交警、路网运行、收费站/互通、清障救援等"
        )
    )
    action: str = Field(description="措施名称，如 封闭第2车道/限速80/情报板提示/诱导分流/拖车救援")
    target: str | None = Field(default=None, description="下发对象/范围，如 K123-K130 上行")
    channel: str | None = Field(default=None, description="下发渠道/载体，如 情报板/APP/广播/对讲/电话/系统工单")
    eta_minutes: int | None = Field(default=None, ge=0, description="建议完成时效（分钟），未知填 null")
    priority: int = Field(default=3, ge=1, le=5, description="1最高5最低")
    rationale: str | None = Field(default=None, description="为什么这么做")


class RiskAssessment(BaseModel):
    risk_level: RiskLevel = Field(default=RiskLevel.UNKNOWN)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    suggested_actions: list[ControlAction] = Field(default_factory=list)


class PipelineResult(BaseModel):
    input_text: str
    uploaded_filename: str | None = None
    uploaded_mime: str | None = None
    ocr_markdown: str | None = None
    ocr_plain_text: str | None = None
    # For single-file OCR this is a dict; for multi-file OCR it's a list of dicts.
    ocr_raw: Any | None = None
    extract: IncidentExtract
    assessment: RiskAssessment
    raw_llm_extract_text: str | None = None
    raw_llm_extract: dict[str, Any] | None = None
    raw_llm_assess_text: str | None = None
    raw_llm_assess: dict[str, Any] | None = None
    # Multi-agent traces (token-saver metadata + per-agent IO summaries)
    agent_metadata_catalog: list[dict[str, Any]] | None = None
    agent_traces: list[dict[str, Any]] | None = None
    dispatch_payloads: list[dict[str, Any]] | None = None
    agent_artifacts: dict[str, Any] | None = None
