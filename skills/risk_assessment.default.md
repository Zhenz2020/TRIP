---
name: risk-assessment-default
agent: risk-assessment
description: 风险研判默认技能：只输出风险等级与原因，不生成处置措施。
inputs: [event_text, incident_extract_draft, constraints_compact]
outputs: [risk_assessment_partial]
resources:
  - SiliconFlow chat.completions
---

## Action Guide
1) 输入 `event_text` 与 `incident_extract_draft`。
2) 输出 `RiskAssessment`，但 `suggested_actions` 必须是空数组 `[]`。
3) 严格 JSON 输出；若解析/校验失败，执行一次 JSON 修复后重试。

