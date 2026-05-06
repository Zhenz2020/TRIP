from __future__ import annotations

from .schemas import IncidentExtract, RiskAssessment, RiskLevel


def rule_based_risk(extract: IncidentExtract) -> RiskAssessment:
    """
    Very small deterministic fallback. LLM can do better, but this keeps the demo stable.
    """
    reasons: list[str] = []

    if extract.hazmat is True:
        reasons.append("涉及危化品/危货，按高风险处置")
        level = RiskLevel.II
    elif extract.casualties and any(k in extract.casualties for k in ["死亡", "重伤"]):
        reasons.append("存在人员伤亡风险")
        level = RiskLevel.II
    elif extract.lanes_blocked and any(k in extract.lanes_blocked for k in ["全封", "封闭", "两", "2", "三", "3"]):
        reasons.append("多车道占用/封闭，易引发大范围拥堵与二次事故")
        level = RiskLevel.III
    else:
        level = RiskLevel.IV

    # Provide a tiny cross-department baseline set so UI can render meaningful sections.
    base_actions = [
        {
            "department": "路网运行/指挥",
            "action": "启动事件跟踪与信息汇聚",
            "target": extract.road_name or extract.location_desc or "事发路段",
            "channel": "指挥调度",
            "eta_minutes": 5,
            "priority": 2,
            "rationale": "建立统一口径，避免信息不一致导致处置延误",
        },
        {
            "department": "诱导大屏",
            "action": "发布行车提示与减速慢行信息",
            "target": extract.stake or (extract.road_name or "事发路段"),
            "channel": "情报板",
            "eta_minutes": 5,
            "priority": 2,
            "rationale": "提前告知降低追尾与二次事故风险",
        },
        {
            "department": "路面处置/清障救援",
            "action": "派遣巡查/清障力量前往现场核查与处置",
            "target": extract.stake or (extract.road_name or "事发路段"),
            "channel": "救援调度",
            "eta_minutes": 15,
            "priority": 2,
            "rationale": "尽快恢复通行能力，缩短占道时间",
        },
    ]
    return RiskAssessment(
        risk_level=level,
        confidence=0.4,
        reasons=reasons,
        suggested_actions=base_actions,  # pydantic will coerce to ControlAction
    )
