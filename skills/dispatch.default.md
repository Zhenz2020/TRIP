---
name: dispatch-default
agent: dispatch
description: 决策下发默认技能：把分部门任务清单整理为对接 payload 草稿（不做真实对接）。
inputs: [risk_assessment_with_actions]
outputs: [dispatch_payloads]
resources: []
---

## Action Guide
1) 按 `department` 分组任务清单。
2) 生成每部门一个 `dispatch_payload`（包含任务列表与风险等级）。
3) 不调用外部系统，仅产出可对接结构。

