from __future__ import annotations

import json
import time
from pathlib import Path

import streamlit as st

from trip_ai.config import load_settings
from trip_ai.llm_siliconflow import SiliconFlowClient
from trip_ai.multi_agent import MultiAgentApp
from trip_ai.agents.core import GlobalContext
from trip_ai.pipeline import run_pipeline  # text-only fallback for now
from trip_ai.skill_loader import load_skills, skills_by_agent, skill_to_dict
from trip_ai.history_store import list_runs, load_run, save_run


st.set_page_config(page_title="TRIP \u9ad8\u901f\u4e8b\u6545\u5de5\u5355\u667a\u80fd\u7814\u5224", layout="wide")

st.markdown(
    """
<style>
  :root{
    --bg0:#F6F8FC;
    --bg1:#FFFFFF;
    --card: rgba(15,23,42,0.04);
    --card2: rgba(15,23,42,0.06);
    --stroke: rgba(15,23,42,0.10);
    --text:#0B1220;
    --muted: rgba(11,18,32,0.66);
    --acc:#0EA5E9;
    --acc2:#22C55E;
    --warn:#F59E0B;
  }
  .stApp{
    background:
      radial-gradient(1200px 600px at 12% 8%, rgba(14,165,233,0.10), transparent 60%),
      radial-gradient(900px 500px at 88% 18%, rgba(34,197,94,0.10), transparent 55%),
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
    background: rgba(255,255,255,0.72);
    font-size: 12px;
    color: var(--muted);
  }
  .hero{
    border:1px solid var(--stroke);
    border-radius:18px;
    padding:16px 18px;
    background: linear-gradient(135deg, rgba(14,165,233,0.10), rgba(34,197,94,0.10));
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
  .prio1{ border-color: rgba(239,68,68,0.45); color: rgba(185,28,28,0.95); background: rgba(239,68,68,0.08); }
  .prio2{ border-color: rgba(245,158,11,0.45); color: rgba(146,64,14,0.95); background: rgba(245,158,11,0.10); }
  .prio3{ border-color: rgba(14,165,233,0.45); color: rgba(3,105,161,0.95); background: rgba(14,165,233,0.10); }
  .prio4{ border-color: rgba(15,23,42,0.18); background: rgba(15,23,42,0.03); }
  .prio5{ border-color: rgba(15,23,42,0.14); background: rgba(15,23,42,0.02); }
</style>
""",
    unsafe_allow_html=True,
)

st.title("TRIP \u9ad8\u901f\u4e8b\u6545\u5de5\u5355\u667a\u80fd\u7814\u5224\uff08MVP\uff09")

settings = load_settings()

# Session state defaults must be set before sidebar widgets read them.
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []
if "run_step_outputs" not in st.session_state:
    st.session_state.run_step_outputs = []
if "run_step_selected" not in st.session_state:
    st.session_state.run_step_selected = 0
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "run_heartbeat_ts" not in st.session_state:
    st.session_state.run_heartbeat_ts = 0.0
if "inspector_needs_refresh" not in st.session_state:
    st.session_state.inspector_needs_refresh = False
if "last_run_done" not in st.session_state:
    st.session_state.last_run_done = False
if "default_samples_loaded" not in st.session_state:
    st.session_state.default_samples_loaded = False

# Auto-load local sample images for a friendlier first-run experience.
if (not st.session_state.default_samples_loaded) and (not st.session_state.uploaded_files):
    try:
        loaded = []
        for name in ("\u5de5\u53551.png", "\u4e8b\u65451.png"):
            p = Path(name)
            if p.exists():
                loaded.append({"filename": name, "mime": "image/png", "bytes": p.read_bytes()})
        if loaded:
            st.session_state.uploaded_files = loaded
    except Exception:
        pass
    st.session_state.default_samples_loaded = True


def _render_run_inspector_sidebar(*, disabled: bool = False) -> None:
    st.subheader("\u8fd0\u884c\u68c0\u67e5\u5668")
    # Avoid interrupting an in-flight run: any widget interaction triggers a rerun and aborts the current script.
    running_recent = bool(st.session_state.is_running) and (
        time.time() - float(st.session_state.run_heartbeat_ts or 0.0) < 60.0
    )
    if running_recent:
        st.caption("\u6b63\u5728\u8fd0\u884c\u4e2d\uff0c\u6682\u65f6\u9501\u5b9a\u68c0\u67e5\u5668\u4ea4\u4e92\uff0c\u8bf7\u7b49\u5f85\u672c\u6b21\u8fd0\u884c\u5b8c\u6210\u3002")
        if st.session_state.run_step_outputs:
            st.json(st.session_state.run_step_outputs[-1])
        return

    if not st.session_state.run_step_outputs:
        st.caption("\u6682\u65e0\u8fd0\u884c\u8f93\u51fa\uff0c\u8bf7\u5148\u8fd0\u884c\u4e00\u6b21\u3002")
        return

    steps = st.session_state.run_step_outputs
    opts = [f"{i+1}. {s.get('agent_name','')}" for i, s in enumerate(steps)]
    st.session_state.run_step_selected = st.selectbox(
        "\u9009\u62e9\u6b65\u9aa4",
        options=list(range(len(steps))),
        format_func=lambda i: opts[i],
        index=min(int(st.session_state.run_step_selected), len(steps) - 1),
        key="run_inspector_step",
        disabled=disabled,
    )
    st.json(steps[int(st.session_state.run_step_selected)])

# Sidebar inspector uses a placeholder that we can update after a run without forcing rerun.
_sidebar_inspector_ph = st.sidebar.empty()
_sidebar_live_inspector_ph = st.sidebar.empty()



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
            f'border:1px solid {b};border-radius:999px;background:{c};color:var(--text);'
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
    latest_ph = st.empty()
    details_ph = st.container()

    states = ["pending"] * len(agents)
    if "run_step_outputs" not in st.session_state:
        st.session_state.run_step_outputs = []
    else:
        # Caller may reset it before running; keep as-is.
        st.session_state.run_step_outputs = list(st.session_state.run_step_outputs)

    st.session_state.is_running = True
    for idx, agent in enumerate(agents):
        st.session_state.run_heartbeat_ts = time.time()
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

        # Persist step snapshots so user can browse previous outputs.
        # Store the latest trace as snapshot for this step.
        snap = ctx.traces[-1] if ctx.traces else {"agent_name": agent.name, "output_summary": "(no trace)"}
        st.session_state.run_step_outputs.append(snap if isinstance(snap, dict) else snap.__dict__)
        # During execution, show only the latest step output (widgets can't be interacted with mid-run anyway).
        with latest_ph:
            st.markdown(f"**Step {idx+1}/{len(agents)} - {agent.name}**")
            st.json(st.session_state.run_step_outputs[-1])
        # Keep the sidebar inspector "alive" during a long run on Streamlit Cloud.
        # We only show the latest step while running to avoid any interactive widgets.
        with _sidebar_live_inspector_ph.container():
            st.subheader("\u8fd0\u884c\u68c0\u67e5\u5668")
            st.caption("\u8fd0\u884c\u4e2d\uff1a\u5b9e\u65f6\u66f4\u65b0\uff08\u4ec5\u663e\u793a\u6700\u65b0\u4e00\u6b65\uff09")
            st.json(st.session_state.run_step_outputs[-1])

    stepper_ph.markdown(
        f"<div class=\"card\">{_render_stepper(labels, states)}</div>",
        unsafe_allow_html=True,
    )
    with progress_ph:
        st.progress(1.0)

    # Inspector is rendered in the sidebar to avoid page jumps on reruns.
    st.session_state.run_heartbeat_ts = time.time()
    st.session_state.is_running = False
    # After the run completes, the main sidebar will render the full inspector (with the step selectbox).
    # Keep this "live" area minimal to avoid duplicate widget keys in the same script run.
    with _sidebar_live_inspector_ph.container():
        st.subheader("\u8fd0\u884c\u68c0\u67e5\u5668")
        st.caption("\u8fd0\u884c\u5df2\u5b8c\u6210\uff0c\u8bf7\u5728\u4e0a\u65b9\u68c0\u67e5\u5668\u9009\u62e9\u6b65\u9aa4\u67e5\u770b\u5386\u53f2\u8f93\u51fa\u3002")
    return ctx


with _sidebar_inspector_ph.container():
    running_recent = bool(st.session_state.is_running) and (
        time.time() - float(st.session_state.run_heartbeat_ts or 0.0) < 60.0
    )
    st.header("\u914d\u7f6e\u72b6\u6001")
    st.write("PaddleOCR token:", "OK" if settings.paddle_ocr_token else "\u7f3a\u5931\uff08\u4ec5\u6587\u672c\u53ef\u7528\uff09")
    st.write(
        "SiliconFlow keys:",
        f"{len(settings.siliconflow_api_keys)} \u4e2a" if settings.siliconflow_api_keys else "\u7f3a\u5931",
    )
    st.write("\u6a21\u578b:", settings.siliconflow_model)
    st.write("\u89c6\u89c9\u6a21\u578b:", settings.siliconflow_vision_model)
    st.caption("\u5bc6\u94a5\u8bf7\u653e\u5230 `.streamlit/secrets.toml`\uff0c\u4e0d\u8981\u5199\u8fdb\u4ee3\u7801\u6216\u63d0\u4ea4\u4ed3\u5e93\u3002")

    st.divider()
    st.subheader("Skills\uff08\u53ef\u70ed\u63d2\u62d4\uff09")
    all_skills = load_skills("skills")
    by_agent = skills_by_agent(all_skills)
    agent_order = [
        ("event-understanding", "\u4e8b\u4ef6\u7406\u89e3"),
        ("knowledge-retrieval", "\u77e5\u8bc6\u8c03\u53d6"),
        ("risk-assessment", "\u98ce\u9669\u7814\u5224"),
        ("plan-generation", "\u65b9\u6848\u751f\u6210"),
        ("dispatch", "\u51b3\u7b56\u4e0b\u53d1"),
    ]
    selected: dict[str, object] = {}
    for agent_key, label in agent_order:
        opts = by_agent.get(agent_key, [])
        opt_names = [s.metadata.name for s in opts]
        if not opt_names:
            st.caption(f"{label}: \u672a\u627e\u5230 skills/{agent_key}.*.md\uff0c\u4f7f\u7528\u5185\u7f6e\u6280\u80fd")
            continue
        choice = st.selectbox(
            f"{label}",
            options=opt_names,
            index=0,
            key=f"skill_{agent_key}",
            disabled=running_recent,
        )
        picked = next((s for s in opts if s.metadata.name == choice), None)
        if picked:
            selected[agent_key] = picked
            with st.expander(f"{label} - Metadata", expanded=False):
                st.json(skill_to_dict(picked)["metadata"])

    st.divider()
    st.subheader("\u8fd0\u884c\u5386\u53f2")
    runs = list_runs()
    if runs:
        options = [f"{r['created_at']}  {r['run_id']}  {r.get('title','')}".strip() for r in runs]
        sel = st.selectbox(
            "\u9009\u62e9\u4e00\u6b21\u8fd0\u884c",
            options=options,
            index=0,
            key="history_select",
            disabled=running_recent,
        )
        run_id = sel.split()[1] if sel.split() else ""
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("\u52a0\u8f7d\u5230\u7ed3\u679c\u9875", key="history_load", disabled=running_recent):
                blob = load_run(run_id)
                if blob and blob.get("result"):
                    from trip_ai.schemas import PipelineResult

                    st.session_state.pipeline_result = PipelineResult.model_validate(blob["result"])
                    st.session_state._history_loaded = run_id
        with col_b:
            if st.button("\u5220\u9664\u8bb0\u5f55\u6587\u4ef6\uff08\u624b\u52a8\uff09", disabled=True, key="history_delete_disabled"):
                pass
    else:
        st.caption("\u6682\u65e0\u5386\u53f2\u8bb0\u5f55\uff0c\u8fd0\u884c\u4e00\u6b21\u540e\u4f1a\u81ea\u52a8\u4fdd\u5b58\u3002")

    st.divider()
    with _sidebar_live_inspector_ph.container():
        _render_run_inspector_sidebar(disabled=running_recent)

# Single-page flow: input -> run -> show results inline (no result sub-tab).
st.subheader("\u8f93\u5165")
st.caption("\u53ef\u4e0a\u4f20\u56fe\u7247/PDF\uff08\u8d70 OCR\uff09\uff0c\u4e5f\u53ef\u9009\u586b\u8865\u5145\u6587\u672c\uff1b\u4e24\u8005\u4f1a\u878d\u5408\u540e\u518d\u8fdb\u5165\u5927\u6a21\u578b\u3002")

col1, col2 = st.columns([1, 1], gap="large")
with col1:
    # Streamlit uploader can't be pre-filled, so provide one-click default samples.
    sample_a = "\u5de5\u53551.png"
    sample_b = "\u4e8b\u65451.png"
    col_s1, col_s2 = st.columns([1, 1], gap="small")
    with col_s1:
        if st.button("\u4f7f\u7528\u9ed8\u8ba4\u793a\u4f8b", key="use_default_samples"):
            loaded = []
            for name in (sample_a, sample_b):
                try:
                    loaded.append({"filename": name, "mime": "image/png", "bytes": Path(name).read_bytes()})
                except Exception as e:  # noqa: BLE001
                    st.error(f"\u8bfb\u53d6\u793a\u4f8b\u5931\u8d25\uff1a{name} ({e})")
            if loaded:
                st.session_state.uploaded_files = loaded
    with col_s2:
        if st.button("\u6e05\u7a7a\u5df2\u9009", key="clear_selected"):
            st.session_state.uploaded_files = []

    up_list = st.file_uploader(
        "\u56fe\u7247/PDF \u5de5\u5355\uff08\u53ef\u9009\uff09",
        type=["png", "jpg", "jpeg", "pdf"],
        accept_multiple_files=True,
    )
    if up_list:
        names = ", ".join([u.name for u in up_list])
        st.caption(f"\u5df2\u9009\u62e9\uff1a{names}")
    elif st.session_state.uploaded_files:
        st.caption(
            "\u5df2\u9009\u62e9\uff1a"
            + ", ".join([f.get("filename", "") for f in st.session_state.uploaded_files if f.get("filename")])
        )

    # Preview selected images (uploaded or default samples).
    preview_files = []
    if up_list:
        preview_files = [{"filename": u.name, "mime": u.type, "bytes": u.getvalue()} for u in up_list]
    elif st.session_state.uploaded_files:
        preview_files = list(st.session_state.uploaded_files)
    if preview_files:
        st.markdown("**\u9884\u89c8**")
        for f in preview_files:
            if (f.get("mime") or "").startswith("image/") and f.get("bytes"):
                st.image(f["bytes"], caption=f.get("filename") or "image", use_container_width=True)
with col2:
    user_text = st.text_area(
        "\u8865\u5145\u6587\u672c\uff08\u53ef\u9009\uff09",
        height=180,
        placeholder="\u4f8b\u5982\uff1a\u63a5\u8b66\u8865\u5145\u4fe1\u606f/\u73b0\u573a\u7535\u8bdd\u56de\u62a5/\u5df2\u91c7\u53d6\u63aa\u65bd/\u5e0c\u671b\u6a21\u578b\u91cd\u70b9\u5173\u6ce8\u70b9\u2026",
    )

run_btn = st.button("\u5f00\u59cb\u7814\u5224", type="primary", disabled=not bool(settings.siliconflow_api_keys))

if run_btn:
    # Uploader files take precedence; otherwise fall back to default samples (if selected).
    files_for_run = []
    if up_list:
        files_for_run = [{"filename": u.name, "mime": u.type, "bytes": u.getvalue()} for u in up_list]
    elif st.session_state.uploaded_files:
        files_for_run = list(st.session_state.uploaded_files)

    if (not files_for_run) and not user_text.strip():
        st.error("\u8bf7\u81f3\u5c11\u63d0\u4f9b\u4e00\u4e2a\u8f93\u5165\uff1a\u4e0a\u4f20\u6587\u4ef6\u6216\u586b\u5199\u8865\u5145\u6587\u672c\u3002")
    elif files_for_run and not settings.paddle_ocr_token:
        st.error("\u4f60\u4e0a\u4f20\u4e86\u6587\u4ef6\uff0c\u4f46\u7f3a\u5c11 PADDLE_OCR_TOKEN\uff0c\u65e0\u6cd5\u8fdb\u884c OCR\u3002\u8bf7\u914d\u7f6e `.streamlit/secrets.toml`\u3002")
    else:
        with st.status("\u5904\u7406\u4e2d\u2026", expanded=True) as status:
            st.session_state.run_step_outputs = []
            st.session_state.run_step_selected = 0

            st.session_state.uploaded_files = files_for_run

            st.write("1/2 \u521d\u59cb\u5316\u5927\u6a21\u578b\u5ba2\u6237\u7aef\u2026")
            client = SiliconFlowClient(settings)

            st.write("2/2 \u591a\u667a\u80fd\u4f53\u7f16\u6392\u6267\u884c\uff08\u4e8b\u4ef6\u7406\u89e3\u2192\u77e5\u8bc6\u8c03\u53d6\u2192\u98ce\u9669\u7814\u5224\u2192\u65b9\u6848\u751f\u6210\u2192\u51b3\u7b56\u4e0b\u53d1\uff09\u2026")
            ctx = GlobalContext(
                working_memory={
                    "settings": settings,
                    "llm_client": client,
                    "uploaded_files": st.session_state.uploaded_files,
                    "input_text": user_text.strip(),
                    "skills_override": selected,
                }
            )
            ctx = run_agents_interactive(ctx)

            res = ctx.working_memory.get("final_result")
            if res is None:
                from trip_ai.schemas import PipelineResult, IncidentExtract, RiskAssessment, RiskLevel

                assessment = ctx.working_memory.get("risk_assessment_with_actions")
                extract = ctx.working_memory.get("incident_extract_draft")
                if assessment is None:
                    assessment = RiskAssessment(
                        risk_level=RiskLevel.UNKNOWN, confidence=0.0, reasons=[], suggested_actions=[]
                    )
                if extract is None:
                    extract = IncidentExtract(confidence=0.0, evidence=[])

                artifacts = {
                    "event_text": ctx.working_memory.get("event_text"),
                    "dispatch_payloads": ctx.working_memory.get("dispatch_payloads"),
                    "user_text": user_text.strip(),
                }

                res = PipelineResult(
                    input_text=ctx.working_memory.get("event_text") or user_text.strip(),
                    uploaded_filename=(", ".join([u.name for u in up_list]) if up_list else None),
                    uploaded_mime=(up_list[0].type if up_list else None),
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
                    agent_traces=[(t if isinstance(t, dict) else t.__dict__) for t in ctx.traces],
                    dispatch_payloads=ctx.working_memory.get("dispatch_payloads"),
                    agent_artifacts=artifacts,
                )

            st.session_state.pipeline_result = res
            try:
                # Persist run history (no binaries) for later replay/debug.
                title = (up_list[0].name if up_list else "") or (user_text.strip()[:20] if user_text else "")
                save_run(result_dict=res.model_dump(), title=title)
            except Exception:
                pass
            status.update(label="\u5b8c\u6210", state="complete")
            st.success("\u5df2\u751f\u6210\u7814\u5224\u7ed3\u679c\uff0c\u8bf7\u7ee7\u7eed\u67e5\u770b\u4e0b\u65b9\u201c\u7ba1\u63a7\u4e0b\u53d1\u201d\u3002")

st.divider()
st.subheader("\u7ba1\u63a7\u4e0b\u53d1")
res = st.session_state.pipeline_result
if not res:
    st.info("\u8fd8\u6ca1\u6709\u7ed3\u679c\u3002\u8bf7\u5148\u8fd0\u884c\u4e00\u6b21\u3002")
else:
    st.markdown(
            f"""
<div class="hero">
  <div class="titleline">
    <div>
      <div style="font-size:18px; font-weight:650;">\u4e0b\u53d1\u6e05\u5355\uff08\u6309\u90e8\u95e8\uff09</div>
      <div class="muted" style="margin-top:4px;">\u7ed3\u679c\u9875\u4ec5\u5c55\u793a\u6700\u7ec8\u4e0b\u53d1\u5185\u5bb9\uff1b\u8fc7\u7a0b\u7ec6\u8282\u5728\u8fd0\u884c\u65f6\u5b9e\u65f6\u67e5\u770b\u3002</div>
    </div>
    <div>
      <span class="chip">\u6a21\u578b\uff1a{settings.siliconflow_model}</span>
      <span class="chip">\u98ce\u9669\u7b49\u7ea7\uff1a{getattr(res, 'assessment', None).risk_level if getattr(res, 'assessment', None) else 'UNKNOWN'}</span>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    payloads = getattr(res, "dispatch_payloads", None) or []
    if not payloads:
        st.warning("\u6ca1\u6709\u751f\u6210 dispatch_payloads\uff08\u53ef\u80fd\u4e0a\u6e38\u5931\u8d25\u6216\u672a\u4ea7\u51fa\u63aa\u65bd\uff09\u3002")
    else:
        default_dept = "\u672a\u5206\u914d"
        dept_tabs = st.tabs([f"{p.get('department', default_dept)}({len(p.get('tasks',[]))})" for p in payloads])
        for tab, pld in zip(dept_tabs, payloads):
            with tab:
                tasks = pld.get("tasks") or []
                for i, a in enumerate(tasks, start=1):
                    prio = int(a.get("priority") or 3)
                    cls = f"prio{min(max(prio,1),5)}"
                    header = f"{i}. {a.get('action') or ''}".strip()
                    target = a.get("target") or ""
                    channel = a.get("channel") or ""
                    eta = a.get("eta_minutes")
                    eta_s = f"{eta} min" if isinstance(eta, int) else ""
                    rationale = a.get("rationale") or ""
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

    st.markdown("### \u4e0b\u8f7d")
    payload = res.model_dump()
    st.download_button(
        "\u4e0b\u8f7d JSON",
        data=json.dumps(payload, ensure_ascii=False, indent=2),
        file_name="trip_result.json",
        mime="application/json",
    )

    with st.expander("\u8fd0\u884c\u8f68\u8ff9\uff08\u53ef\u9009\uff09", expanded=False):
        if getattr(res, "agent_traces", None):
            st.json(res.agent_traces)
        else:
            st.info("\u65e0 traces\u3002")

