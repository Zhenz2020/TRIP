---
name: plan-generation-default
agent: plan-generation
description: 方案生成默认技能：按部门职责模板生成可执行任务清单（派单）。
inputs: [event_text, incident_extract_draft, risk_assessment_partial, playbook_full]
outputs: [risk_assessment_with_actions]
resources:
  - SiliconFlow chat.completions
  - trip_ai.department_playbook.DEPARTMENT_PLAYBOOK
---

## Action Guide
1) 严格遵循 playbook 与硬约束生成 `suggested_actions`（覆盖>=3部门，每部门>=2条）。
2) 每条措施必须含：department、action、priority、channel、target、eta_minutes、rationale。
3) 禁止复述原文整句，输出要任务化/参数化。
4) 严格 JSON；失败则一次修复后重试。

