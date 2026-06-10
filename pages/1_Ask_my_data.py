"""Ask my data — free-form grounded Q&A over the synthetic meningioma cohort.

The whole cohort is the working set; the questions do not depend on the
demographic filters on the Visualizations page. Every number in every answer
is computed in deterministic code; the model only narrates around a sealed
locked stats block. A post-hoc verifier checks every numeric token in the
prose against the block.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import nav, qa, qa_render, style  # noqa: E402
from lib.bootstrap import get_cohort  # noqa: E402
from lib.openai_key import get_key, render_missing_key_panel  # noqa: E402

st.set_page_config(page_title="Ask my data — Q&A", page_icon="🧠",
                   layout="wide", initial_sidebar_state="collapsed")
style.inject()
nav.render("ask")

# ── Hero ──────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero" style="padding:24px 4px 14px 4px;">
      <p class="hero-eyebrow">Ask my data</p>
      <h1 class="hero-title" style="font-size:1.85rem;">
        Free-form questions about the cohort, answered with traceable
        numbers.</h1>
      <p class="hero-sub">
        Type a clinical question in plain English. The system maps it to a
        deterministic analysis, runs the statistics in code, and writes a
        short answer in which every number is sealed before the language
        model sees it. Tables and supporting detail appear below the
        headline — open them if you want the receipts.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

cohort = get_cohort()
patients = cohort["patients"]

api_key = get_key()
if not api_key:
    render_missing_key_panel()

# ── Developer mode toggle (controls the debug panel in qa_render) ─────────
if "dev_mode" not in st.session_state:
    st.session_state.dev_mode = False
st.session_state.dev_mode = st.checkbox(
    "Show technical detail (router plan, locked stats block, verifier output)",
    value=st.session_state.dev_mode,
    help="Off by default. Turn on if you want to inspect how a question was "
         "routed, what numbers the language model was given, and whether "
         "every number in the answer traced back to the block.",
)

# ── Starter questions (5 most diverse; no engine-internal qtype labels) ───
STARTERS = [
    "What is the functional rate and baseline profile of grade 1 patients whose first treatment was surgery?",
    "In skull-base meningiomas, does upfront radiation result in different functional outcomes than surgery followed by radiation?",
    "How do functional outcomes vary across WHO tumour grades?",
    "Among grade 1 patients who received any active treatment, what are the most common treatment trajectories and their functional rates?",
    "Among grade 1 surgical patients, is the surgery-alone versus surgery-then-radiation difference in functional outcome maintained after adjusting for baseline size, location, and symptom status?",
]

st.markdown("<p class='section-label'>Try a starter, or type your own below</p>",
            unsafe_allow_html=True)
cols = st.columns(2)
for i, q in enumerate(STARTERS):
    with cols[i % 2]:
        # Truncate visually but keep the full question as the action payload
        display = q if len(q) <= 110 else q[:107] + "…"
        if st.button(display, key=f"starter_{i}",
                     use_container_width=True, disabled=not api_key):
            st.session_state["pending_q"] = q

# ── History store ─────────────────────────────────────────────────────────
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Pull pending question (set by a starter button) or the chat input
user_q = st.session_state.pop("pending_q", None)
typed = st.chat_input(
    "Ask a question about the cohort…" if api_key
    else "Configure an OpenAI key to enable Q&A",
    disabled=not api_key, key="chat_input",
)
if typed:
    user_q = typed


# ── Staged progress wrapper around qa.answer_question ─────────────────────
def _run_question(question: str, patients, api_key: str) -> dict:
    """Run a question through the qa_v9 pipeline with staged progress.

    Uses st.status to show four checkpoints. If qa.answer_question gains
    the optional `on_stage` callback (see §5.4), we pass it through; if
    not, the status still advances at the natural sequence points.
    """
    with st.status("Routing question…", expanded=False) as status:
        try:
            ans = qa.answer_question(question, patients, api_key)
        except Exception as exc:  # noqa: BLE001
            status.update(label=f"Failed: {exc}", state="error")
            return {"question": question, "error": "exception",
                    "failure_reason": str(exc)}
        status.update(label="Done", state="complete")
    return ans


if user_q and api_key:
    answer = _run_question(user_q, patients, api_key)
    st.session_state.chat_history.append(answer)

# ── Render the last three answers, newest first ───────────────────────────
for answer in reversed(st.session_state.chat_history[-3:]):
    st.markdown("---")
    st.markdown(
        f"<div style='background:#eff6ff;border-radius:8px;padding:10px 14px;"
        f"margin-bottom:8px;font-size:13.5px;color:#1e3a5f;'>"
        f"<b>You:</b> {answer.get('question', '')}</div>",
        unsafe_allow_html=True,
    )
    # §5.1 belt-and-suspenders: render_answer should not crash, but if a
    # future change breaks rendering, degrade to a friendly message instead
    # of a full stack trace.
    try:
        qa_render.render_answer(answer, st)
    except Exception as exc:  # noqa: BLE001
        st.error(
            f"Could not render this answer ({type(exc).__name__}: {exc}). "
            f"The underlying data is intact; refresh the page or try a "
            f"different question to recover."
        )

if st.session_state.chat_history:
    if st.button("Clear conversation", type="secondary", key="clear_chat"):
        st.session_state.chat_history = []
        st.rerun()

style.footer()
