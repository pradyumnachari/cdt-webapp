"""Visualizations — descriptive cohort statistics, treatment-flow diagrams,
and extraction provenance for the synthetic meningioma cohort.

Filter the cohort by demographics or tumour profile; the page recomputes
summary statistics live. Secondary breakdowns and the data-quality panel
are folded into expanders so the headline numbers and pathway view stay
above the fold.
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import nav, qa, style  # noqa: E402
from lib.bootstrap import get_cohort  # noqa: E402
from lib.buckets import ACTION_COLORS, ACTION_LABELS  # noqa: E402
from lib.engine import cohort_stats, quality_summary  # noqa: E402
from lib.figures import (build_action_outcome_sankey,  # noqa: E402
                         build_trajectory_sankey)

st.set_page_config(page_title="Visualizations — Ask my data",
                   page_icon="🧠", layout="wide",
                   initial_sidebar_state="collapsed")
style.inject()
nav.render("viz")

# ── Hero ──────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero" style="padding:24px 4px 14px 4px;">
      <p class="hero-eyebrow">Visualizations</p>
      <h1 class="hero-title" style="font-size:1.85rem;">
        Filter the cohort, see the headline numbers and the treatment
        flow.</h1>
      <p class="hero-sub">
        Pick any combination of grade, location, age band, and gender.
        Functional-outcome rates and the treatment-flow diagram update
        live. Secondary breakdowns and the data-quality panel are
        collapsed by default — open them when you want detail.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

cohort = get_cohort()
patients = cohort["patients"]


# ── Cohort filters ────────────────────────────────────────────────────────
def _opts(field_path) -> list:
    vals = set()
    for r in patients.values():
        d = r
        for k in field_path:
            d = d[k]
        vals.add(d)
    return ["(all)"] + sorted(str(v) for v in vals)


f1, f2, f3, f4 = st.columns(4)
with f1:
    grade = st.selectbox("Grade", _opts(["stratification", "grade"]))
with f2:
    loc = st.selectbox("Location", _opts(["stratification", "location"]))
with f3:
    age = st.selectbox("Age band", _opts(["stratification", "age"]))
with f4:
    gender = st.selectbox("Gender", _opts(["stratification", "gender"]))


def _keep(r: dict) -> bool:
    s = r["stratification"]
    return ((grade == "(all)" or s["grade"] == grade)
            and (loc == "(all)" or s["location"] == loc)
            and (age == "(all)" or s["age"] == age)
            and (gender == "(all)" or s["gender"] == gender))


filtered = {p: r for p, r in patients.items() if _keep(r)}
if not filtered:
    st.warning("No patients match the current filters.")
    style.footer()
    st.stop()

# ── Headline stats ────────────────────────────────────────────────────────
stats = cohort_stats(filtered)
st.markdown("<p class='section-label'>Functional outcomes (filtered cohort)</p>",
            unsafe_allow_html=True)
rate = stats["functional_rate"]
lo, hi = qa.clopper_pearson(stats["n_functional"], stats["n_outcome_known"])
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


# ── Treatment-pathway view (primary, kept visible) ────────────────────────
st.markdown("<p class='section-label'>Treatment pathways</p>",
            unsafe_allow_html=True)
view = st.radio(
    "Pathway view",
    ["State → Treatment → Outcome", "L1 → L2 → Outcome"],
    horizontal=True, label_visibility="collapsed",
)
recs = list(filtered.values())
fig = (build_action_outcome_sankey(recs)
       if view.startswith("State") else build_trajectory_sankey(recs))
if fig is not None:
    st.plotly_chart(fig, use_container_width=True)


# ── Secondary breakdowns (collapsed) ──────────────────────────────────────
def _rate_bar(title, data, color_map=None):
    if not data:
        st.caption("No data.")
        return
    labels, rates, texts, colors = [], [], [], []
    for key, (k, n) in data.items():
        labels.append(str(key).replace("_", " "))
        rates.append(k / n if n else 0)
        texts.append(f"{(k / n if n else 0):.0%} (n={n})")
        colors.append((color_map or {}).get(key, "#2563eb"))
    fig = go.Figure(go.Bar(x=labels, y=rates, text=texts,
                          textposition="outside", marker_color=colors))
    fig.update_layout(
        title=dict(text=title, font=dict(size=13)),
        yaxis=dict(range=[0, 1.18], tickformat=".0%", gridcolor="#f1f5f9"),
        xaxis=dict(showgrid=False), height=280,
        margin=dict(t=42, b=20, l=10, r=10),
        plot_bgcolor="white", paper_bgcolor="white", showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


with st.expander("Breakdowns by grade and first action", expanded=False):
    b1, b2 = st.columns(2)
    with b1:
        _rate_bar("Functional rate by grade", stats["by_grade"])
    with b2:
        al = {ACTION_LABELS.get(a, a): v
              for a, v in stats["by_first_action"].items()}
        cl = {ACTION_LABELS.get(a, a): ACTION_COLORS.get(a, "#2563eb")
              for a in stats["by_first_action"]}
        _rate_bar("Functional rate by first action", al, cl)


# ── Data quality (collapsed) ──────────────────────────────────────────────
with st.expander("Extraction data quality", expanded=False):
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
                f"<p style='font-size:11.5px;color:#475569;margin:2px 0 0 0;'>"
                f"{count / te:.1%} of {q['total_events']} events</p></div>",
                unsafe_allow_html=True,
            )

style.footer()
