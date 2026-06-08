"""Recommendation — full decision detail for one patient at one level."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import nav, style                                    # noqa: E402
from lib.bootstrap import get_cohort                           # noqa: E402
from lib.buckets import ACTION_COLORS, ACTION_LABELS, ACTIONS  # noqa: E402
from lib.config import TOP_K_SIMILAR                           # noqa: E402
from lib.data_loader import reconstruct_note                   # noqa: E402
from lib.engine import (counterfactuals, practice_recommendation,  # noqa: E402
                        recommend, retrieve_similar)

st.set_page_config(page_title="Recommendation — CDT", page_icon="🧠",
                   layout="wide", initial_sidebar_state="collapsed")
style.inject()
nav.render("recommendation")

cohort = get_cohort()
patients = cohort["patients"]
train = cohort["train"]

# ── Resolve selected patient / level ───────────────────────────────────────
default_pid = next(iter(cohort["test"] or patients))
pid = st.session_state.get("selected_pid", default_pid)
if pid not in patients:
    pid = default_pid
patient = patients[pid]

levels = sorted(patient["levels"])
sel_level = st.session_state.get("selected_level", levels[0])
if sel_level not in levels:
    sel_level = levels[0]

# ── Patient header + level selector ────────────────────────────────────────
top_l, top_r = st.columns([2.4, 1])
with top_l:
    st.markdown(
        f"<p class='hero-eyebrow' style='margin-bottom:4px;'>"
        f"Patient {patient['display_id']}</p>"
        f"<h1 style='font-size:1.55rem;margin:0 0 6px 0;'>"
        f"{patient['headline']}</h1>",
        unsafe_allow_html=True,
    )
with top_r:
    sel_level = st.selectbox(
        "Decision level", levels, index=levels.index(sel_level),
        format_func=lambda L: f"Level {L}",
    )
st.session_state["selected_pid"] = pid
st.session_state["selected_level"] = sel_level

li = patient["levels"][sel_level]

# patient state strip
demo = patient["demographics"]
strip = [
    ("Age", f"{int(demo['age'])}" if demo.get("age") else "—"),
    ("Grade", patient["stratification"]["grade"].replace("_", " ")),
    ("Location", patient["stratification"]["location"].replace("_", " ")),
    ("State at L%d" % sel_level, li["state_key"].replace("_", " · ")),
    ("Observed action", ACTION_LABELS[li["action"]]),
]
st.markdown(
    "<div style='display:flex;gap:22px;flex-wrap:wrap;padding:8px 0 10px 0;"
    "border-bottom:1px solid #e2e8f0;margin-bottom:18px;'>"
    + "".join(
        f"<div><div style='font-size:10.5px;text-transform:uppercase;"
        f"letter-spacing:0.08em;color:#94a3b8;font-weight:600;'>{k}</div>"
        f"<div style='font-size:14px;font-weight:600;color:#0f172a;'>{v}</div>"
        f"</div>"
        for k, v in strip
    )
    + "</div>",
    unsafe_allow_html=True,
)

# ── Recommendation (two signals) ───────────────────────────────────────────
rec = recommend(patient, sel_level, train)
prac = practice_recommendation(patient, sel_level, train)

best = rec["best_action"]            # outcome-optimal
practice = prac["best_action"]       # most common among similar patients
obs = rec["observed_action"]
p = rec["p_by_action"]
freq = prac["freq_by_action"]

signals_agree = best == practice
if signals_agree:
    verdict = (f"Both signals point to "
               f"<span class='headline-action'>{ACTION_LABELS[best]}</span> — "
               f"a consistent recommendation.")
else:
    verdict = (f"The two signals diverge — outcome-optimal favours "
               f"<span class='headline-action'>{ACTION_LABELS[best]}</span>, "
               f"while most similar patients received "
               f"<span class='headline-action'>{ACTION_LABELS[practice]}</span>. "
               f"A case worth a closer look.")

st.markdown(
    f"""
    <div class="headline-card">
      <p class="headline-card-eyebrow">Recommendation · Level {sel_level}</p>
      <p class="headline-card-body">
        {verdict} The clinician's observed choice was
        <span class="headline-action">{ACTION_LABELS[obs]}</span>.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# two-signal summary row
def _signal_card(title: str, action: str, detail: str) -> str:
    return (
        f"<div style='flex:1;min-width:220px;border:1px solid #e2e8f0;"
        f"border-radius:10px;padding:14px 16px;background:#fff;'>"
        f"<div style='font-size:10.5px;text-transform:uppercase;"
        f"letter-spacing:0.09em;color:#64748b;font-weight:700;'>{title}</div>"
        f"<div style='font-size:1.05rem;font-weight:700;color:#0f172a;"
        f"margin:5px 0 3px 0;'>{ACTION_LABELS[action]}</div>"
        f"<div style='font-size:11.5px;color:#64748b;'>{detail}</div></div>"
    )


p_best = p.get(best)
st.markdown(
    "<div style='display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px;'>"
    + _signal_card(
        "Outcome-optimal", best,
        (f"Highest estimated P(functional) = {p_best:.0%}"
         if p_best is not None else "No outcome support at this stage"))
    + _signal_card(
        "Practice-based (most common)", practice,
        f"{freq[practice]:.0%} of similar patients at this stage")
    + "</div>",
    unsafe_allow_html=True,
)

p_obs = p.get(obs)
sc1, sc2, sc3 = st.columns(3)
for col, label, value in [
    (sc1, "P(functional) — outcome-optimal",
     f"{p_best:.0%}" if p_best is not None else "—"),
    (sc2, "P(functional) — observed",
     f"{p_obs:.0%}" if p_obs is not None else "no support"),
    (sc3, "Similar patients at this stage", f"{prac['n_total']}"),
]:
    with col:
        st.markdown(
            f"<div class='stat-card'><p class='stat-card-label'>{label}</p>"
            f"<p class='stat-card-value'>{value}</p></div>",
            unsafe_allow_html=True,
        )

# ── Two charts: outcome by action  +  what similar patients chose ──────────
st.markdown("<p class='section-label'>Outcome-optimal vs. practice-based</p>",
            unsafe_allow_html=True)
ch_l, ch_r = st.columns(2)

with ch_l:
    acts = [a for a in ACTIONS if p.get(a) is not None]
    fig1 = go.Figure(go.Bar(
        x=[ACTION_LABELS[a] for a in acts],
        y=[p[a] for a in acts],
        marker_color=[ACTION_COLORS[a] for a in acts],
        text=[f"{p[a]:.0%}" for a in acts], textposition="outside",
    ))
    fig1.update_layout(
        title=dict(text="P(functional outcome) per action",
                   font=dict(size=12.5)),
        yaxis=dict(range=[0, 1.15], tickformat=".0%", gridcolor="#f1f5f9"),
        xaxis=dict(showgrid=False),
        height=270, margin=dict(t=42, b=20, l=10, r=10),
        plot_bgcolor="white", paper_bgcolor="white", showlegend=False,
    )
    st.plotly_chart(fig1, use_container_width=True)
    st.caption("Similarity-weighted functional-outcome rate among "
               "level-matched patients who took each action.")

with ch_r:
    fa = [a for a in ACTIONS]
    fig2 = go.Figure(go.Bar(
        x=[ACTION_LABELS[a] for a in fa],
        y=[freq[a] for a in fa],
        marker_color=[ACTION_COLORS[a] for a in fa],
        text=[f"{freq[a]:.0%}<br>(n={prac['count_by_action'][a]})"
              for a in fa],
        textposition="outside",
    ))
    fig2.update_layout(
        title=dict(text="What similar patients chose at this stage",
                   font=dict(size=12.5)),
        yaxis=dict(range=[0, 1.18], tickformat=".0%", gridcolor="#f1f5f9"),
        xaxis=dict(showgrid=False),
        height=270, margin=dict(t=42, b=20, l=10, r=10),
        plot_bgcolor="white", paper_bgcolor="white", showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True)
    st.caption("Similarity-weighted share of level-matched patients choosing "
               "each action — observed practice, independent of outcome.")

# ── Evidence: similar patients ─────────────────────────────────────────────
st.markdown("<p class='section-label'>Evidence — similar historical patients</p>",
            unsafe_allow_html=True)
similar = retrieve_similar(patient, train, TOP_K_SIMILAR)
st.markdown(
    f"<div class='info-line'>The estimate is grounded in the "
    f"<b>{len(similar)} most archetype-similar</b> training patients, each "
    f"weighted by closeness.</div>",
    unsafe_allow_html=True,
)
for rank, item in enumerate(similar, 1):
    tp = item["record"]
    lvl = sel_level if sel_level in tp["levels"] else tp["max_level"]
    tli = tp["levels"][lvl]
    out = tp["outcome"]["functional_status"]
    oc = "#16a34a" if out == "functional" else (
        "#ea580c" if out == "impaired" else "#94a3b8")
    st.markdown(
        f"""
        <div style='display:flex;align-items:center;gap:14px;
                    padding:8px 12px;border:1px solid #e2e8f0;
                    border-radius:8px;margin-bottom:6px;'>
          <div style='flex:0 0 26px;font-weight:700;color:#2563eb;'>#{rank}</div>
          <div style='flex:1;font-size:13px;'>{tp['headline']}</div>
          <div style='flex:0 0 130px;font-size:12px;color:#475569;'>
            L{lvl}: {ACTION_LABELS[tli['action']]}</div>
          <div style='flex:0 0 90px;font-size:12px;font-weight:600;
                      color:{oc};'>{out.title()}</div>
          <div style='flex:0 0 70px;font-size:11px;color:#94a3b8;
                      text-align:right;'>sim {item['similarity']:.2f}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Counterfactual table (all levels) ──────────────────────────────────────
st.markdown("<p class='section-label'>Counterfactual analysis — all levels</p>",
            unsafe_allow_html=True)
st.caption("ΔU = U(optimal) − U(observed), where U(a) = P(functional | a). "
           "Positive ΔU means the model would have preferred a different "
           "action.")
cf = counterfactuals(patient, train)
cf_disp = pd.DataFrame([{
    "Level": c["level"],
    "State": c["state_key"].replace("_", " · "),
    "Observed": ACTION_LABELS[c["observed"]],
    "Outcome-optimal": ACTION_LABELS[c["optimal"]],
    "Practice-based": ACTION_LABELS[c["practice"]],
    "U(opt)": f"{c['u_optimal']:.2f}",
    "U(obs)": f"{c['u_observed']:.2f}",
    "ΔU": f"{c['delta_u']:+.3f}",
    "n_eff": f"{c['n_eff']:.1f}",
} for c in cf])
st.dataframe(cf_disp, use_container_width=True, hide_index=True)

# ── Reconstructed clinical note ────────────────────────────────────────────
st.markdown("<p class='section-label'>Clinical pathway (up to this level)</p>",
            unsafe_allow_html=True)
note = reconstruct_note(patient, sel_level)
st.markdown(
    f"<div style='font-size:12.5px;line-height:1.7;color:#334155;"
    f"max-height:300px;overflow-y:auto;background:#f8fafc;padding:12px 14px;"
    f"border-radius:6px;border:1px solid #e2e8f0;'>"
    f"{note.replace(chr(10), '<br/>')}</div>",
    unsafe_allow_html=True,
)

# ── Data quality for this patient ──────────────────────────────────────────
q = patient["quality"]
flags = [
    ("Copy-paste suspected", q["n_copy_paste"]),
    ("Uncertain facts", q["n_uncertain"]),
    ("Inferred tumour size", q["n_size_inferred"]),
    ("Date inconsistencies", q["n_date_flag"]),
    ("External-institution events", q["n_external"]),
]
if any(c for _, c in flags):
    st.markdown("<p class='section-label'>Extraction data quality</p>",
                unsafe_allow_html=True)
    chips = "".join(
        f"<span class='method-pill method-baseline'>{label}: {c}</span>"
        for label, c in flags if c
    )
    st.markdown(
        f"<div style='padding:4px 0 2px 0;'>{chips}</div>"
        f"<div class='warn-line'>These provenance flags come from the "
        f"extraction step. They are shown so the recommendation is read in "
        f"light of the underlying note quality.</div>",
        unsafe_allow_html=True,
    )

# ── Observed outcome (for evaluation) ──────────────────────────────────────
with st.expander("Reveal observed outcome (for evaluation only)",
                 expanded=False):
    out = patient["outcome"]
    st.markdown(
        f"This patient's recorded functional status at last follow-up was "
        f"**{out['functional_status']}** "
        f"(ECOG {out['ecog_score']}, KPS {out['kps_score']}). "
        f"Use this to audit the recommendation against the observed outcome — "
        f"the model never sees it."
    )

style.footer()
