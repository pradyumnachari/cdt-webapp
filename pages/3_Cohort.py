"""Cohort — filterable descriptive stats + qa_v9 grounded Q&A (v4).

Same layout as v3 page 3 (cohort filters, headline stats, pathway viz, data
quality) but with the Q&A section replaced by the qa_v9 engine: full 9-type
router + structured output panels matching the screenshot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import nav, qa, qa_render, style  # noqa: E402
from lib.bootstrap import get_cohort  # noqa: E402
from lib.buckets import ACTION_COLORS, ACTION_LABELS  # noqa: E402
from lib.engine import cohort_stats, quality_summary  # noqa: E402
from lib.qa import clopper_pearson  # noqa: E402
from lib.figures import (build_action_outcome_sankey,  # noqa: E402
                         build_trajectory_sankey)
from lib.openai_key import get_key, render_missing_key_panel  # noqa: E402

st.set_page_config(page_title="Cohort — CDT v4", page_icon="🧠",
                   layout="wide", initial_sidebar_state="collapsed")
style.inject()
nav.render("cohort")

cohort = get_cohort()
patients = cohort["patients"]

st.markdown(
    """
    <div class="hero" style="padding:30px 4px 16px 4px;">
      <p class="hero-eyebrow">Cohort &amp; grounded Q&amp;A</p>
      <h1 class="hero-title" style="font-size:1.9rem;">
        Explore the cohort, then ask any question.</h1>
      <p class="hero-sub">Filter by demographics or tumour profile to see
      functional-outcome rates and extraction data quality. Then ask a free-form
      question — the v9 engine routes it into one of nine analysis types and
      returns a structured answer with the same panels as a full-paper analysis.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Cohort filters (same as v3) ────────────────────────────────────────────
def _opts(field_path) -> list:
    vals = set()
    for r in patients.values():
        d = r
        for k in field_path: d = d[k]
        vals.add(d)
    return ["(all)"] + sorted(str(v) for v in vals)

f1, f2, f3, f4 = st.columns(4)
with f1: grade = st.selectbox("Grade", _opts(["stratification", "grade"]))
with f2: loc = st.selectbox("Location", _opts(["stratification", "location"]))
with f3: age = st.selectbox("Age band", _opts(["stratification", "age"]))
with f4: gender = st.selectbox("Gender", _opts(["stratification", "gender"]))

def _keep(r: dict) -> bool:
    s = r["stratification"]
    return ((grade == "(all)" or s["grade"] == grade)
            and (loc == "(all)" or s["location"] == loc)
            and (age == "(all)" or s["age"] == age)
            and (gender == "(all)" or s["gender"] == gender))

filtered = {p: r for p, r in patients.items() if _keep(r)}
if not filtered:
    st.warning("No patients match the current filters.")
    style.footer(); st.stop()

# ── Headline stats (same as v3) ────────────────────────────────────────────
stats = cohort_stats(filtered)
st.markdown("<p class='section-label'>Functional outcomes (filtered cohort)</p>",
            unsafe_allow_html=True)
rate = stats["functional_rate"]
lo, hi = clopper_pearson(stats["n_functional"], stats["n_outcome_known"])
m1, m2, m3 = st.columns(3)
for col, label, value in [
    (m1, "Patients (filtered)", stats["n"]),
    (m2, "Functional at last follow-up",
     f"{rate:.1%}" if rate is not None else "—"),
    (m3, "95% CI",
     f"{lo:.1%} – {hi:.1%}" if rate is not None else "—"),
]:
    with col:
        st.markdown(
            f"<div class='stat-card'><p class='stat-card-label'>{label}</p>"
            f"<p class='stat-card-value'>{value}</p></div>",
            unsafe_allow_html=True,
        )

def _rate_bar(title, data, color_map=None):
    if not data: st.caption("No data."); return
    labels, rates, texts, colors = [], [], [], []
    for key, (k, n) in data.items():
        labels.append(str(key).replace("_", " "))
        rates.append(k/n if n else 0)
        texts.append(f"{(k/n if n else 0):.0%} (n={n})")
        colors.append((color_map or {}).get(key, "#2563eb"))
    fig = go.Figure(go.Bar(x=labels, y=rates, text=texts,
                          textposition="outside", marker_color=colors))
    fig.update_layout(title=dict(text=title, font=dict(size=13)),
                     yaxis=dict(range=[0, 1.18], tickformat=".0%", gridcolor="#f1f5f9"),
                     xaxis=dict(showgrid=False), height=280,
                     margin=dict(t=42, b=20, l=10, r=10),
                     plot_bgcolor="white", paper_bgcolor="white", showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

b1, b2 = st.columns(2)
with b1: _rate_bar("Functional rate by grade", stats["by_grade"])
with b2:
    al = {ACTION_LABELS.get(a, a): v for a, v in stats["by_first_action"].items()}
    cl = {ACTION_LABELS.get(a, a): ACTION_COLORS.get(a, "#2563eb")
          for a in stats["by_first_action"]}
    _rate_bar("Functional rate by first action", al, cl)

# ── Treatment-pathway visualization (same as v3) ───────────────────────────
st.markdown("<p class='section-label'>Treatment pathways</p>",
            unsafe_allow_html=True)
view = st.radio("Pathway view",
               ["State → Treatment → Outcome", "L1 → L2 → Outcome"],
               horizontal=True, label_visibility="collapsed")
recs = list(filtered.values())
fig = (build_action_outcome_sankey(recs)
       if view.startswith("State") else build_trajectory_sankey(recs))
if fig is not None:
    st.plotly_chart(fig, use_container_width=True)

# ── Data quality (same as v3) ──────────────────────────────────────────────
st.markdown("<p class='section-label'>Extraction data quality</p>",
            unsafe_allow_html=True)
q = quality_summary(filtered)
te = q["total_events"] or 1
qc = st.columns(5)
for col, label, count in [
    (qc[0], "Copy-paste suspected", q["copy_paste"]),
    (qc[1], "Uncertain facts", q["uncertain"]),
    (qc[2], "Inferred tumour size", q["size_inferred"]),
    (qc[3], "Date inconsistencies", q["date_flag"]),
    (qc[4], "External-institution events", q["external"]),
]:
    with col:
        st.markdown(
            f"<div class='stat-card'><p class='stat-card-label'>{label}</p>"
            f"<p class='stat-card-value'>{count}</p>"
            f"<p style='font-size:11px;color:#94a3b8;margin:2px 0 0 0;'>"
            f"{count/te:.1%} of {q['total_events']} events</p></div>",
            unsafe_allow_html=True,
        )

# =========================================================================
# Grounded Q&A — v9 engine
# =========================================================================
st.markdown("<p class='section-label' style='margin-top:30px;'>Ask a question (v9 engine)</p>",
            unsafe_allow_html=True)
st.markdown(
    "<div class='info-line'>Free-form questions. The router (gpt-4o) classifies "
    "the question into one of 9 types; the executor runs Fisher / "
    "Cochran-Mantel-Haenszel / IPW / E-value as appropriate; the synthesizer "
    "writes prose with every number grounded in the locked stats block. "
    "Operates on the WHOLE cohort, independent of the filters above.</div>",
    unsafe_allow_html=True,
)

api_key = get_key()
if not api_key:
    render_missing_key_panel()

# Starter questions covering the 9 question types
STARTERS_V9 = [
    ("FACTUAL",              "How many grade 1 patients are in the cohort?"),
    ("DESCRIPTIVE",          "What is the functional rate and baseline profile of grade 1 patients whose first treatment was surgery?"),
    ("COMPARATIVE",          "In skull-base meningiomas, does upfront radiation result in different functional outcomes than surgery followed by radiation?"),
    ("SUBGROUP-COMPARATIVE", "How do functional outcomes vary across WHO tumour grades?"),
    ("TEMPORAL-CONDITIONAL", "Among grade 2 surgery-first patients, do those who received radiation within 6 months of surgery have better functional outcomes than those who went to watchful waiting first?"),
    ("PATHWAY-FUNNEL",       "What percentage of grade 2 patients follow the surgery-then-radiation pathway versus alternatives, and do functional outcomes differ?"),
    ("TRAJECTORY",           "Among grade 1 patients who received any active treatment, what are the most common treatment trajectories and their functional rates?"),
    ("COMPARATIVE-ADJUSTED", "Among grade 1 surgical patients, is the surgery-alone versus surgery-then-radiation difference in functional outcome maintained after adjusting for baseline size, location, and symptom status?"),
    ("DESCRIPTIVE-TEMPORAL", "Among grade 1 patients who began with watchful waiting, what fraction later escalated and at what median time from diagnosis?"),
]

st.markdown("<p style='font-size:12px;color:#64748b;margin:6px 0 8px 0;'>"
            "Pick a starter (one per question type) or type your own below.</p>",
            unsafe_allow_html=True)
sc1, sc2 = st.columns(2)
for i, (qt, q) in enumerate(STARTERS_V9):
    with (sc1 if i % 2 == 0 else sc2):
        if st.button(f"[{qt}] {q[:70]}{'...' if len(q) > 70 else ''}",
                    key=f"starter_v9_{i}", use_container_width=True,
                    disabled=not api_key):
            st.session_state["pending_q_v9"] = q

if "chat_history_v9" not in st.session_state:
    st.session_state.chat_history_v9 = []

user_q = st.session_state.pop("pending_q_v9", None)
typed = st.chat_input(
    "Ask a question about the cohort…" if api_key
    else "Configure an OpenAI key to enable Q&A",
    disabled=not api_key, key="chat_input_v9",
)
if typed: user_q = typed

if user_q and api_key:
    with st.spinner("Routing question, computing statistics, composing answer…"):
        try:
            answer = qa.answer_question(user_q, patients, api_key)
        except Exception as e:
            answer = {"question": user_q, "error": "exception",
                     "failure_reason": str(e)}
    st.session_state.chat_history_v9.append(answer)

# Show the most recent 3 answers (newest at top)
for answer in reversed(st.session_state.chat_history_v9[-3:]):
    st.markdown("---")
    st.markdown(
        f"<div style='background:#eff6ff;border-radius:8px;padding:10px 14px;"
        f"margin-bottom:8px;font-size:13.5px;color:#1e3a5f;'>"
        f"<b>You:</b> {answer.get('question', '')}</div>",
        unsafe_allow_html=True,
    )
    qa_render.render_answer(answer, st)

if st.session_state.chat_history_v9:
    if st.button("Clear conversation", type="secondary", key="clear_v9"):
        st.session_state.chat_history_v9 = []
        st.rerun()

style.footer()
