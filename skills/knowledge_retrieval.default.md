---
name: knowledge-retrieval-default
agent: knowledge-retrieval
description: 知识调取默认技能：准备/压缩部门职责模板与硬约束（token友好）。
inputs: [event_text, incident_extract_draft]
outputs: [playbook_compact, constraints_compact]
resources:
  - trip_ai.department_playbook.DEPARTMENT_PLAYBOOK
---

## Action Guide
1) 选择适用的部门职责模板（默认内置 playbook）。
2) 把模板压缩成短上下文（部门列表 + 通用硬约束），减少 token 消耗。
3) 不做推理，不改事实，仅做知识准备。

