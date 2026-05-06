from __future__ import annotations

import json

import streamlit as st

from trip_ai.config import load_settings
from trip_ai.llm_siliconflow import SiliconFlowClient
from trip_ai.multi_agent import MultiAgentApp
from trip_ai.agents.core import GlobalContext
from trip_ai.pipeline import run_pipeline  # text-only fallback for now
from trip_ai.skill_loader import load_skills, skills_by_agent, skill_to_dict


st.set_page_config(page_title="TRIP 高速事故工单智能研判", layout="wide")

st.markdown(
    """
<style>
  :root{
    --bg0:#070A12;
    --bg1:#0B1220;
    --card: rgba(255,255,255,0.06);
    --card2: rgba(255,255,255,0.09);
    --stroke: rgba(255,255,255,0.12);
    --text:#E8F0FF;
    --muted: rgba(232,240,255,0.72);
    --acc:#3DD6D0;
    --acc2:#8A5CFF;
    --warn:#FFB020;
  }
  .stApp{
    background:
      radial-gradient(1200px 600px at 10% 10%, rgba(61,214,208,0.14), transparent 60%),
      radial-gradient(1000px 500px at 90% 20%, rgba(138,92,255,0.14), transparent 55%),
      linear-gradient(180deg, var(--bg0), var(--bg1));
    color: var(--text);
  }
  h1, h2, h3, h4 { letter-spacing: 0.2px; }
  .muted { color: var(--muted); }
  .chip{
    display:inline-block;
    padding:4px 10px;
    margin-right:8px;
    border:1px solid var(--stroke);
    border-radius:999px;
    background: rgba(255,255,255,0.04);
    font-size: 12px;
    color: var(--muted);
  }
  .hero{
    border:1px solid var(--stroke);
    border-radius:18px;
    padding:16px 18px;
    background: linear-gradient(135deg, rgba(61,214,208,0.08), rgba(138,92,255,0.08));
  }
  .card{
    border:1px solid var(--stroke);
    border-radius:16px;
    padding:14px 14px;
    background: var(--card);
  }
  .card:hover{ background: var(--card2); }
  .k{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; font-size: 12px; color: var(--muted); }
  .titleline{ display:flex; align-items:center; justify-content:space-between; gap:12px; }
  .priority{
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
    font-size: 12px;
    padding:2px 8px;
    border-radius:999px;
    border:1px solid var(--stroke);
    color: var(--muted);
  }
  .prio1{ border-color: rgba(255,75,75,0.55); color: rgba(255,200,200,0.95); }
  .prio2{ border-color: rgba(255,176,32,0.55); color: rgba(255,235,200,0.95); }
  .prio3{ border-color: rgba(61,214,208,0.55); color: rgba(210,255,252,0.95); }
  .prio4{ border-color: rgba(200,200,200,0.35); }
  .prio5{ border-color: rgba(200,200,200,0.25); }
</style>
""",
    unsafe_allow_html=True,
)

st.title("TRIP 高速事故工单智能研判（MVP）")

settings = load_settings()



def _render_stepper(labels: list[str], states: list[str]) -> str:
    chips = []
    for i, lab in enumerate(labels):
        stt = states[i]
        if stt == "done":
            c = "rgba(61,214,208,0.20)"
            b = "rgba(61,214,208,0.55)"
        elif stt == "running":
            c = "rgba(138,92,255,0.20)"
            b = "rgba(138,92,255,0.55)"
        elif stt == "fail":
            c = "rgba(255,176,32,0.18)"
            b = "rgba(255,176,32,0.55)"
        else:
            c = "rgba(255,255,255,0.04)"
            b = "rgba(255,255,255,0.12)"
        chips.append(
            f'<span style="display:inline-block;padding:6px 10px;margin-right:8px;margin-bottom:8px;'
            f'border:1px solid {b};border-radius:999px;background:{c};color:rgba(232,240,255,0.86);'
            f'font-size:12px;">{i+1}. {lab}</span>'
        )
    return "".join(chips)


def run_agents_interactive(ctx: GlobalContext) -> GlobalContext:
    # Run agents sequentially with live UI updates.
    from trip_ai.agents.core import add_metadata
    from trip_ai.agents.dispatch import DISPATCH_SKILL
    from trip_ai.agents.event_understanding import EVENT_UNDERSTANDING_SKILL
    from trip_ai.agents.knowledge_retrieval import KNOWLEDGE_RETRIEVAL_SKILL
    from trip_ai.agents.plan_generation import PLAN_GENERATION_SKILL
    from trip_ai.agents.risk_assessment import RISK_ASSESSMENT_SKILL

    skills_override = ctx.working_memory.get("skills_override") or {}
    add_metadata(
        ctx,
        skills_override.get("event-understanding", EVENT_UNDERSTANDING_SKILL),
        skills_override.get("knowledge-retrieval", KNOWLEDGE_RETRIEVAL_SKILL),
        skills_override.get("risk-assessment", RISK_ASSESSMENT_SKILL),
        skills_override.get("plan-generation", PLAN_GENERATION_SKILL),
        skills_override.get("dispatch", DISPATCH_SKILL),
    )

    agents = MultiAgentApp.default().orchestrator.agents
    labels = [a.name for a in agents]

    stepper_ph = st.empty()
    progress_ph = st.empty()
    details_ph = st.empty()

    states = ["pending"] * len(agents)
    for idx, agent in enumerate(agents):
        states[idx] = "running"
        stepper_ph.markdown(
            f"<div class=\"card\">{_render_stepper(labels, states)}</div>",
            unsafe_allow_html=True,
        )
        with progress_ph:
            st.progress((idx) / max(len(agents), 1))

        # Run agent
        try:
            ctx = agent.run(ctx=ctx)
            states[idx] = "done"
        except Exception as e:  # noqa: BLE001
            states[idx] = "fail"
            # Keep orchestration alive; record failure in traces.
            ctx.traces.append(
                {
                    "agent_name": agent.name,
                    "skill_name": getattr(agent, "skill").metadata.name if getattr(agent, "skill", None) else "",
                    "input_summary": "[runner]",
                    "output_summary": f"agent failed: {e}",
                    "raw_model_output": None,
                    "resources_used": [],
                }
            )

        with details_ph:
            with st.expander(f"{idx+1}) {agent.name} - ????", expanded=True):
                if ctx.traces:
                    last = ctx.traces[-1]
                    st.json(last if isinstance(last, dict) else last.__dict__)

    stepper_ph.markdown(
        f"<div class=\"card\">{_render_stepper(labels, states)}</div>",
        unsafe_allow_html=True,
    )
    with progress_ph:
        st.progress(1.0)
    return ctx


with st.sidebar:
    st.header("配置状态")
    st.write("PaddleOCR token:", "OK" if settings.paddle_ocr_token else "缺失（仅文本可用）")
    st.write("SiliconFlow keys:", f"{len(settings.siliconflow_api_keys)} 个" if settings.siliconflow_api_keys else "缺失")
    st.write("模型:", settings.siliconflow_model)
    st.write("视觉模型:", settings.siliconflow_vision_model)
    st.caption("密钥请放到 `.streamlit/secrets.toml`，不要写进代码或提交仓库。")

    st.divider()
    st.subheader("Skills（可热插拔）")
    all_skills = load_skills("skills")
    by_agent = skills_by_agent(all_skills)
    agent_order = [
        ("event-understanding", "事件理解"),
        ("knowledge-retrieval", "知识调取"),
        ("risk-assessment", "风险研判"),
        ("plan-generation", "方案生成"),
        ("dispatch", "决策下发"),
    ]
    selected: dict[str, object] = {}
    for agent_key, label in agent_order:
        opts = by_agent.get(agent_key, [])
        opt_names = [s.metadata.name for s in opts]
        if not opt_names:
            st.caption(f"{label}: 未找到 skills/{agent_key}.*.md，使用内置技能")
            continue
        default_idx = 0
        choice = st.selectbox(f"{label}", options=opt_names, index=default_idx, key=f"skill_{agent_key}")
        picked = next((s for s in opts if s.metadata.name == choice), None)
        if picked:
            selected[agent_key] = picked
            with st.expander(f"{label} - Metadata", expanded=False):
                st.json(skill_to_dict(picked)["metadata"])

tab_upload, tab_result = st.tabs(["上传与处理", "结果"])

if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None
if "uploaded_file" not in st.session_state:
    st.session_state.uploaded_file = None

with tab_upload:
    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.subheader("方式 A：上传图片/PDF 工单（OCR）")
        up = st.file_uploader("选择文件", type=["png", "jpg", "jpeg", "pdf"])
        ocr_btn = st.button("OCR + 研判", type="primary", disabled=not bool(settings.siliconflow_api_keys))
        st.caption("图片/PDF 走 OCR；之后进入大模型抽取与研判。")

    with col2:
        st.subheader("方式 B：直接粘贴文本工单")
        text_in = st.text_area("工单文本", height=220, placeholder="粘贴事故工单文本…")
        text_btn = st.button("文本研判", disabled=not bool(settings.siliconflow_api_keys))

    if ocr_btn:
        if not up:
            st.error("请先上传图片或 PDF。")
        elif not settings.paddle_ocr_token:
            st.error("缺少 PADDLE_OCR_TOKEN，无法进行 OCR。请配置 `.streamlit/secrets.toml`。")
        else:
            with st.status("处理中…", expanded=True) as status:
                st.session_state.uploaded_file = {
                    "filename": up.name,
                    "mime": up.type,
                    "bytes": up.getvalue(),
                }
                st.write("1/2 初始化大模型客户端…")
                client = SiliconFlowClient(settings)
                st.write("2/2 多智能体编排执行（事件理解→知识调取→风险研判→方案生成→决策下发）…")
                ctx = GlobalContext(
                    working_memory={
                        "settings": settings,
                        "llm_client": client,
                        "uploaded_file": st.session_state.uploaded_file,
                        "input_text": "",
                        "skills_override": selected,
                    }
                )
                ctx = run_agents_interactive(ctx)
                # Pack into PipelineResult-like object for UI reuse
                res = ctx.working_memory.get("final_result")
                if res is None:
                    # Construct minimal display payload from ctx artifacts
                    from trip_ai.schemas import PipelineResult

                    assessment = ctx.working_memory.get("risk_assessment_with_actions")
                    extract = ctx.working_memory.get("incident_extract_draft")
                    artifacts = {
                        # Event understanding
                        "event_text": ctx.working_memory.get("event_text"),
                        "ocr_markdown": ctx.working_memory.get("ocr_markdown"),
                        "ocr_plain_text": ctx.working_memory.get("ocr_plain_text"),
                        "ocr_raw": ctx.working_memory.get("ocr_raw"),
                        "vision_text": ctx.working_memory.get("vision_text"),
                        "incident_extract_draft": extract.model_dump() if extract else None,
                        "raw_llm_extract_text": ctx.working_memory.get("raw_llm_extract_text"),
                        "raw_llm_extract": ctx.working_memory.get("raw_llm_extract"),
                        # Knowledge retrieval
                        "playbook_compact": ctx.working_memory.get("playbook_compact"),
                        "constraints_compact": ctx.working_memory.get("constraints_compact"),
                        # Risk assessment
                        "risk_assessment_partial": (
                            ctx.working_memory.get("risk_assessment_partial").model_dump()
                            if ctx.working_memory.get("risk_assessment_partial")
                            else None
                        ),
                        "raw_llm_risk_text": ctx.working_memory.get("raw_llm_risk_text"),
                        "raw_llm_risk_json": ctx.working_memory.get("raw_llm_risk_json"),
                        # Plan generation
                        "risk_assessment_with_actions": assessment.model_dump() if assessment else None,
                        "raw_llm_plan_text": ctx.working_memory.get("raw_llm_plan_text"),
                        "raw_llm_plan_json": ctx.working_memory.get("raw_llm_plan_json"),
                        # Dispatch
                        "dispatch_payloads": ctx.working_memory.get("dispatch_payloads"),
                    }
                    res = PipelineResult(
                        input_text=ctx.working_memory.get("event_text") or "",
                        uploaded_filename=up.name,
                        uploaded_mime=up.type,
                        ocr_markdown=ctx.working_memory.get("ocr_markdown"),
                        ocr_plain_text=ctx.working_memory.get("ocr_plain_text"),
                        ocr_raw=ctx.working_memory.get("ocr_raw"),
                        extract=extract,
                        assessment=assessment,
                        raw_llm_extract_text=ctx.working_memory.get("raw_llm_extract_text"),
                        raw_llm_extract=ctx.working_memory.get("raw_llm_extract"),
                        raw_llm_assess_text=ctx.working_memory.get("raw_llm_plan_text"),
                        raw_llm_assess=ctx.working_memory.get("raw_llm_plan_json"),
                        agent_metadata_catalog=[m.__dict__ for m in ctx.metadata_catalog],
                        agent_traces=[t.__dict__ for t in ctx.traces],
                        dispatch_payloads=ctx.working_memory.get("dispatch_payloads"),
                        agent_artifacts=artifacts,
                    )
                st.session_state.pipeline_result = res
                status.update(label="完成", state="complete")
                st.success("已生成研判结果，切换到“结果”查看。")

    if text_btn:
        if not text_in.strip():
            st.error("请先输入工单文本。")
        else:
            with st.status("处理中…", expanded=True) as status:
                st.write("1/2 初始化大模型客户端…")
                client = SiliconFlowClient(settings)
                st.write("2/2 多智能体编排执行…")
                ctx = GlobalContext(
                    working_memory={
                        "settings": settings,
                        "llm_client": client,
                        "uploaded_file": None,
                        "input_text": text_in.strip(),
                        "skills_override": selected,
                    }
                )
                ctx = run_agents_interactive(ctx)
                from trip_ai.schemas import PipelineResult

                assessment = ctx.working_memory.get("risk_assessment_with_actions")
                extract = ctx.working_memory.get("incident_extract_draft")
                artifacts = {
                    "event_text": ctx.working_memory.get("event_text"),
                    "vision_text": ctx.working_memory.get("vision_text"),
                    "incident_extract_draft": extract.model_dump() if extract else None,
                    "raw_llm_extract_text": ctx.working_memory.get("raw_llm_extract_text"),
                    "raw_llm_extract": ctx.working_memory.get("raw_llm_extract"),
                    "playbook_compact": ctx.working_memory.get("playbook_compact"),
                    "constraints_compact": ctx.working_memory.get("constraints_compact"),
                    "risk_assessment_partial": (
                        ctx.working_memory.get("risk_assessment_partial").model_dump()
                        if ctx.working_memory.get("risk_assessment_partial")
                        else None
                    ),
                    "raw_llm_risk_text": ctx.working_memory.get("raw_llm_risk_text"),
                    "raw_llm_risk_json": ctx.working_memory.get("raw_llm_risk_json"),
                    "risk_assessment_with_actions": assessment.model_dump() if assessment else None,
                    "raw_llm_plan_text": ctx.working_memory.get("raw_llm_plan_text"),
                    "raw_llm_plan_json": ctx.working_memory.get("raw_llm_plan_json"),
                    "dispatch_payloads": ctx.working_memory.get("dispatch_payloads"),
                }
                res = PipelineResult(
                    input_text=ctx.working_memory.get("event_text") or text_in.strip(),
                    extract=extract,
                    assessment=assessment,
                    raw_llm_extract_text=ctx.working_memory.get("raw_llm_extract_text"),
                    raw_llm_extract=ctx.working_memory.get("raw_llm_extract"),
                    raw_llm_assess_text=ctx.working_memory.get("raw_llm_plan_text"),
                    raw_llm_assess=ctx.working_memory.get("raw_llm_plan_json"),
                    agent_metadata_catalog=[m.__dict__ for m in ctx.metadata_catalog],
                    agent_traces=[t.__dict__ for t in ctx.traces],
                    dispatch_payloads=ctx.working_memory.get("dispatch_payloads"),
                    agent_artifacts=artifacts,
                )
                st.session_state.pipeline_result = res
                st.session_state.uploaded_file = None
                status.update(label="完成", state="complete")
                st.success("已生成研判结果，切换到“结果”查看。")

with tab_result:
    st.subheader("????")
    res = st.session_state.pipeline_result
    if not res:
        st.info("?????????\"?????\"??????")
    else:
        st.markdown(
            f"""
<div class="hero">
  <div class="titleline">
    <div>
      <div style="font-size:18px; font-weight:650;">?????????</div>
      <div class="muted" style="margin-top:4px;">??????????????????????????</div>
    </div>
    <div>
      <span class="chip">???{settings.siliconflow_model}</span>
      <span class="chip">?????{res.assessment.risk_level}</span>
    </div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        payloads = getattr(res, "dispatch_payloads", None) or []
        if not payloads:
            st.warning("???? dispatch_payloads????????????????")
        else:
            dept_tabs = st.tabs([f"{p.get('department','???')}?{len(p.get('tasks',[]))}?" for p in payloads])
            for tab, pld in zip(dept_tabs, payloads):
                with tab:
                    tasks = pld.get('tasks') or []
                    for i, a in enumerate(tasks, start=1):
                        prio = int(a.get('priority') or 3)
                        cls = f"prio{min(max(prio,1),5)}"
                        header = f"{i}. {a.get('action') or ''}".strip()
                        target = a.get('target') or ''
                        channel = a.get('channel') or ''
                        eta = a.get('eta_minutes')
                        eta_s = f"{eta} min" if isinstance(eta, int) else ""
                        rationale = a.get('rationale') or ''
                        st.markdown(
                            f"""
<div class="card">
  <div class="titleline">
    <div style="font-size:15px; font-weight:650;">{header}</div>
    <div class="priority {cls}">P{prio}</div>
  </div>
  <div class="k" style="margin-top:8px;">target: {target if target else '-'} | channel: {channel if channel else '-'} | eta: {eta_s if eta_s else '-'}</div>
  <div style="margin-top:10px; color: rgba(232,240,255,0.86);">{rationale}</div>
</div>
""",
                            unsafe_allow_html=True,
                        )

        st.markdown("### ??")
        payload = res.model_dump()
        st.download_button(
            "?? JSON",
            data=json.dumps(payload, ensure_ascii=False, indent=2),
            file_name="trip_result.json",
            mime="application/json",
        )

        with st.expander("????????", expanded=False):
            if getattr(res, "agent_traces", None):
                st.json(res.agent_traces)
            else:
                st.info("? traces?")

