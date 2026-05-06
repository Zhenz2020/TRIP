from __future__ import annotations

from typing import Any


_ACTION_KEYS = ["action", "task", "measure", "content", "措施", "动作", "任务", "建议", "处置措施"]
_DEPT_KEYS = ["department", "dept", "部门", "业务方"]
_TARGET_KEYS = ["target", "scope", "范围", "位置", "路段"]
_CHANNEL_KEYS = ["channel", "渠道", "载体"]
_ETA_KEYS = ["eta_minutes", "eta", "eta_min", "时效", "分钟", "完成时限"]
_PRIO_KEYS = ["priority", "prio", "优先级", "级别"]
_RAT_KEYS = ["rationale", "reason", "说明", "理由", "依据"]


def _pick(d: dict[str, Any], keys: list[str]) -> Any:
    for k in keys:
        if k in d and d[k] is not None and d[k] != "":
            return d[k]
    return None


def normalize_risk_assessment_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Best-effort normalization for model outputs.
    - Coerce suggested_actions list item keys into the schema keys.
    - Keep unknown keys intact to preserve traceability.
    """
    if not isinstance(raw, dict):
        return {}

    actions = raw.get("suggested_actions")
    if actions is None and isinstance(raw.get("actions"), list):
        actions = raw.get("actions")
        raw["suggested_actions"] = actions

    if not isinstance(actions, list):
        return raw

    norm_actions: list[dict[str, Any]] = []
    for item in actions:
        if not isinstance(item, dict):
            continue

        # Preserve original item for traceability.
        out = dict(item)
        if "department" not in out:
            v = _pick(item, _DEPT_KEYS)
            if v is not None:
                out["department"] = v
        if "action" not in out:
            v = _pick(item, _ACTION_KEYS)
            if v is not None:
                out["action"] = v
        if "target" not in out:
            v = _pick(item, _TARGET_KEYS)
            if v is not None:
                out["target"] = v
        if "channel" not in out:
            v = _pick(item, _CHANNEL_KEYS)
            if v is not None:
                out["channel"] = v
        if "eta_minutes" not in out:
            v = _pick(item, _ETA_KEYS)
            if v is not None:
                out["eta_minutes"] = v
        if "priority" not in out:
            v = _pick(item, _PRIO_KEYS)
            if v is not None:
                out["priority"] = v
        if "rationale" not in out:
            v = _pick(item, _RAT_KEYS)
            if v is not None:
                out["rationale"] = v

        norm_actions.append(out)

    raw["suggested_actions"] = norm_actions
    return raw

