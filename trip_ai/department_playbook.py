from __future__ import annotations

# Department responsibility "skill-like" playbook used to steer LLM decisions.
# Keep this concise and editable; it acts like a local policy/knowledge pack.

DEPARTMENT_PLAYBOOK = """
你将输出“按部门分发的可执行处置任务”。请严格遵循以下部门职责模板（playbook）：

1) 路网运行/指挥
- 目标：统一口径、研判升级、资源调度、信息发布节奏
- 可用动作（示例）：启动事件跟踪；建立关键信息清单（时间/位置/方向/占道/伤亡/危化）；通报相关单位；滚动更新；建议启动应急预案等级
- 输出要求：给出需要补核的缺失字段与核实方式（电话/视频/巡查）

2) 诱导大屏（情报板/VMS/可变限速）
- 目标：降低二次事故风险、提前分流、提示减速与占道信息
- 可用动作（示例）：发布“前方事故/占道/减速慢行”；发布绕行/分流建议；联动可变限速（如 80/60）；提示保持车距
- 输出要求：必须包含 channel=情报板/限速系统，target 给出上游区间或关键节点（互通/收费站/K 段）

3) 路面处置/清障救援
- 目标：现场核查、快速清障、恢复通行能力
- 可用动作（示例）：派遣巡查确认；拖车/清障车出动；摆放锥桶与警示；清理抛洒物；设置临时交通组织
- 输出要求：给出到场时效 eta_minutes，并说明优先处置点（占道车道/危化/伤员）

4) 交警/路政协同
- 目标：交通管制、事故快处、执法协同与安全防护
- 可用动作（示例）：现场管制；封闭/借道放行；事故快处取证；协同救护；设置警戒区
- 输出要求：说明需要的管制形式（封闭车道/分段放行/主线封闭等）

5) 收费站/互通管控
- 目标：入口控制、匝道分流、区域绕行组织
- 可用动作（示例）：上游收费站限流/间歇放行；互通匝道分流；引导车辆改走替代路线
- 输出要求：target 明确到收费站/互通名称（若原文没有则给出“需确认”）

通用硬约束：
- suggested_actions 必须覆盖至少 3 个不同 department；每个 department 至少 2 条
- 每条措施必须包含：department、action、priority、channel、target、eta_minutes、rationale
- 禁止复述 OCR 原文句子（不要把原文整句搬进 action/rationale），而要“任务化/参数化”表达
""".strip()

