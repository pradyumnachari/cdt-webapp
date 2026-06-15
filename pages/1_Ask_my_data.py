"""Ask my data — free-form grounded Q&A over the synthetic meningioma cohort."""

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

# ── Page hero ─────────────────────────────────────────────────────────────

st.markdown(
      """
          <div class="hero">
                  <p class="hero-eyebrow">Ask my data</p>
                          <h1 class="hero-title-inner">
                                      Free-form questions about the cohort,<br/>answered with traceable numbers.
                                              </h1>
                                                      <p class="hero-sub-inner">
                                                                  Type a clinical question in plain English. Statistics are computed in
                                                                              code and sealed before the language model writes a single word.
                                                                                          Every number in the answer is verifiable.
                                                                                                  </p>
                                                                                                      </div>
                                                                                                          """,
      unsafe_allow_html=True,
)

cohort   = get_cohort()
patients = cohort["patients"]
api_key  = get_key()

if not api_key:
      render_missing_key_panel()

# ── Dev mode ──────────────────────────────────────────────────────────────

if "dev_mode" not in st.session_state:
      st.session_state.dev_mode = False

with st.expander("Developer options", expanded=False):
      st.session_state.dev_mode = st.checkbox(
                "Show technical detail (router plan, locked stats block, verifier output)",
                value=st.session_state.dev_mode,
      )

# ── Prominent search prompt ───────────────────────────────────────────────

st.markdown(
      """
          <div class="search-prompt">
                  <div class="search-prompt-label">Ask a question</div>
                          Type a clinical question below — for example, "What is the functional
                                  rate for grade 1 patients who had surgery first?" or choose a starter
                                          question from the list below.
                                              </div>
                                                  """,
      unsafe_allow_html=True,
)

# ── Chat input (prominent, at the top) ───────────────────────────────────

if "chat_history" not in st.session_state:
      st.session_state.chat_history = []

user_q = st.session_state.pop("pending_q", None)

typed  = st.chat_input(
      "Ask a question about the cohort…" if api_key else "Configure an OpenAI key to enable Q&A",
      disabled=not api_key,
      key="chat_input",
)

if typed:
      user_q = typed

# ── Starter questions ─────────────────────────────────────────────────────

STARTERS = [
      "What is the functional rate and baseline profile of grade 1 patients whose first treatment was surgery?",
      "In skull-base meningiomas, does upfront radiation result in different functional outcomes than surgery followed by radiation?",
      "How do functional outcomes vary across WHO tumour grades?",
      "Among grade 1 patients who received any active treatment, what are the most common treatment trajectories and their functional rates?",
      "Among grade 1 surgical patients, is the surgery-alone versus surgery-then-radiation difference in functional outcome maintained after adjusting for baseline size, location, and symptom status?",
]

st.markdown("<p class='section-label'>Starter questions</p>", unsafe_allow_html=True)

cols = st.columns(2)
for i, q in enumerate(STARTERS):
      with cols[i % 2]:
                display = q if len(q) <= 110 else q[:107] + "…"
                if st.button(display, key=f"starter_{i}", use_container_width=True, disabled=not api_key):
                              st.session_state["pending_q"] = q

        # ── Run question ──────────────────────────────────────────────────────────

def run_question(question: str, patients, api_key: str) -> dict:
      with st.status("Analysing question…", expanded=False) as status:
                try:
                              ans = qa.answer_question(question, patients, api_key)
except Exception as exc:  # noqa: BLE001
            status.update(label=f"Failed: {exc}", state="error")
            return {"question": question, "error": "exception", "failure_reason": str(exc)}
        status.update(label="Done", state="complete")
    return ans

if user_q and api_key:
      answer = run_question(user_q, patients, api_key)
      st.session_state.chat_history.append(answer)

# ── Render answers ────────────────────────────────────────────────────────

for answer in reversed(st.session_state.chat_history[-3:]):
      st.markdown("---")
      st.markdown(
          f"<div style='background:#0a0f1a;border:1px solid #1e3a5f;border-radius:8px;"
          f"padding:10px 14px;margin-bottom:8px;font-size:13.5px;color:#93c5fd;'>"
          f"<b>You:</b> {answer.get('question', '')}</div>",
          unsafe_allow_html=True,
      )
      try:
                qa_render.render_answer(answer, st)
except Exception as exc:  # noqa: BLE001
        st.error(f"Could not render this answer ({type(exc).__name__}: {exc}). Try a different question.")

if st.session_state.chat_history:
      if st.button("Clear conversation", type="secondary", key="clear_chat"):
                st.session_state.chat_history = []
                st.rerun()

  style.footer()
