"""Similar patients & evidence — retrospective per-patient evidence panel.

Pick a patient and a decision level. The page shows, for that exact decision
point, what the patient actually received, what archetype-similar historical
patients received, and what their functional outcomes were. There is NO
recommendation, NO "optimal action", and NO counterfactual analysis —
the page is descriptive evidence the clinician can read and judge.

Folds in the picker + exemplar tiles previously at `pages/1_Try_it.py` and
the supporting panels previously at `pages/2_Recommendation.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import nav, style                                       # noqa: E402
from lib.bootstrap import get_cohort                              # noqa: E402
from lib.buckets import ACTION_COLORS, ACTION_LABELS, ACTIONS     # noqa: E402
from lib.config import TOP_K_SIMILAR                              # noqa: E402
from lib.data_loader import reconstruct_note                      # noqa: E402
# `counterfactuals` is used internally by `pick_exemplars` to score
# illustrative cases, but its output is NOT rendered as a counterfactual
# table — the table is intentionally absent.
from lib.engine import (counterfactuals, practice_recommendation,  # noqa: E402
                        recommend, retrieve_similar)

st.set_page_config(page_title="Similar patients & evidence — Ask my data",
                   page_icon="🧠", layout="wide",
                   initial_sidebar_state="collapsed")
style.inject()
nav.render("similar")

cohort = get_cohort()
patients = cohort["patients"]
train = cohort["train"]
test = cohort["test"]


# ── Auto-pick illustrative cases (neutral tags, no "model agrees") ────────
@st.cache_data(show_spinner="Selecting illustrative cases…")
def pick_exemplars() -> list:
    """Choose 3 patients that each tell a different descriptive story.

    Tags are neutral (no prescriptive language). ΔU from `counterfactuals`
    is used as a *signal of how distinct a case is*, NOT as a recommendation.
    """
    scored = []
    pool = test if test else patients
    for pid, rec in pool.items():
        try:
            cfs = counterfactuals(rec, train)
        except Exception:  # noqa: BLE001
            continue
        total_du = sum(c["delta_u"] for c in cfs)
        best_level = max(cfs, key=lambda c: c["delta_u"])["level"] if cfs else 1
        scored.append({
            "pid": pid, "rec": rec, "total_du": total_du,
            "best_level": best_level, "n_cf": len(cfs),
        })
    if not scored:
        return []

    chosen, used = [], set()

    def take(item, tag, color, story):
        if item and item["pid"] not in used:
            used.add(item["pid"])
            chosen.append({**item, "tag": tag, "tag_color": color,
                           "story": story})

    by_du = sorted(scored, key=lambda s: s["total_du"], reverse=True)
    take(by_du[0],
         "Notable treatment / outcome contrast (illustrative)",
         "#7c3aed",
         "The observed trajectory looks different from what historical "
         "archetype-similar patients with the best functional outcomes "
         "received.")

    g23 = [s for s in scored
           if s["rec"]["stratification"]["grade"] in ("grade_2", "grade_3")]
    if g23:
        take(max(g23, key=lambda s: s["total_du"]),
             "Higher grade", "#0891b2",
             "Atypical or anaplastic tumour — a harder, higher-risk case.")

    young = sorted(scored,
                   key=lambda s: s["rec"]["demographics"].get("age") or 999)
    take(young[0], "Younger patient", "#d97706",
         "Young patient — long horizon weighs on the watch-vs-treat call.")

    return chosen[:3]


# ── Hero ──────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero" style="padding:24px 4px 14px 4px;">
      <p class="hero-eyebrow">Similar patients & evidence</p>
      <h1 class="hero-title" style="font-size:1.85rem;">
        For one patient at one decision point, see what archetype-similar
        patients received and how they did.</h1>
      <p class="hero-sub">
        Pick a patient and a decision level. The panels below show the
        observed treatment, what historical archetype-similar patients
        chose at the same point, and the functional-outcome rate associated
        with each treatment in that group. This is descriptive evidence,
        not a recommendation.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)


def _select(pid: str, level: int) -> None:
    st.session_state["selected_pid"] = pid
    st.session_state["selected_level"] = level
    st.rerun()


# ── Exemplar tiles ────────────────────────────────────────────────────────
exemplars = pick_exemplars()
if exemplars:
    st.markdown("<p class='section-label'>Illustrative cases</p>",
                unsafe_allow_html=True)
    cols = st.columns(len(exemplars))
    for col, ex in zip(cols, exemplars):
        rec = ex["rec"]
        with col:
            st.markdown(
                f"""
                <div class="tile">
                  <div>
                    <span class="tile-chip"
                          style="background:{ex['tag_color']};">
                      {ex['tag']}</span>
                  </div>
                  <p class="tile-headline">{rec['headline']}</p>
                  <p class="tile-story">{ex['story']}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"Open patient {rec['display_id']}",
                         key=f"ex_{ex['pid']}", use_container_width=True):
                _select(ex["pid"], ex["best_level"])


# ── Patient picker ────────────────────────────────────────────────────────
st.markdown("<p class='section-label'>Pick a patient</p>",
            unsafe_allow_html=True)
split_choice = st.radio(
    "Cohort", ["Held-out patients", "All patients"],
    horizontal=True, label_visibility="collapsed",
)
pool = test if (split_choice == "Held-out patients" and test) else patients
default_pid = st.session_state.get("selected_pid") or next(iter(pool or patients))
if default_pid not in pool:
    default_pid = next(iter(pool))
options = sorted(pool.keys())
pid = st.selectbox(
    "Patient", options,
    index=options.index(default_pid) if default_pid in options else 0,
    format_func=lambda p: f"{pool[p]['display_id']} — {pool[p]['headline']}",
)
patient = pool[pid]
levels = sorted(patient["levels"])
default_level = st.session_state.get("selected_level", levels[0])
if default_level not in levels:
    default_level = levels[0]

# Patient header + state strip
st.markdown("---")
top_l, top_r = st.columns([2.4, 1])
with top_l:
    st.markdown(
        f"<p class='hero-eyebrow' style='margin-bottom:4px;'>"
        f"Patient {patient['display_id']}</p>"
        f"<h2 style='font-size:1.4rem;margin:0 0 6px 0;'>"
        f"{patient['headline']}</h2>",
        unsafe_allow_html=True,
    )
with top_r:
    sel_level = st.selectbox(
        "Decision level", levels,
        index=levels.index(default_level),
        format_func=lambda L: f"Level {L}",
        help="Each decision level is a clinical decision point in the "
             "patient's pathway (L1 = first treatment decision, L2 = next "
             "decision, …). Pick the level you want to inspect — the page "
             "shows what was observed there and how archetype-similar "
             "patients were treated at the same point.",
    )
st.session_state["selected_pid"] = pid
st.session_state["selected_level"] = sel_level

li = patient["levels"][sel_level]
demo = patient["demographics"]
strip = [
    ("Age", f"{int(demo['age'])}" if demo.get("age") else "—"),
    ("Grade", patient["stratification"]["grade"].replace("_", " ")),
    ("Location", patient["stratification"]["location"].replace("_", " ")),
    (f"State at L{sel_level}", li["state_key"].replace("_", " · ")),
    ("Observed action", ACTION_LABELS[li["action"]]),
]
st.markdown(
    "<div style='display:flex;gap:22px;flex-wrap:wrap;padding:8px 0 10px 0;"
    "border-bottom:1px solid #e2e8f0;margin-bottom:18px;'>"
    + "".join(
        f"<div><div style='font-size:12px;text-transform:uppercase;"
        f"letter-spacing:0.08em;color:#475569;font-weight:600;'>{k}</div>"
        f"<div style='font-size:14px;font-weight:600;color:#0f172a;'>{v}</div>"
        f"</div>"
        for k, v in strip
    )
    + "</div>",
    unsafe_allow_html=True,
)

# ── Compute the underlying numbers (engine, not a recommender) ────────────
rec = recommend(patient, sel_level, train)
prac = practice_recommendation(patient, sel_level, train)
practice = prac["best_action"]
obs = rec["observed_action"]
p_by_action = rec["p_by_action"]
freq = prac["freq_by_action"]

# ── Descriptive framing block (the analysis the page is doing) ────────────
st.markdown(
    f"""
    <div class="info-line" style="font-size:13.5px;">
      <b>At decision L{sel_level}, this patient actually received
      <span style="color:#0f172a;">{ACTION_LABELS[obs]}</span>.</b>
      The panels below show:
      <ul style="margin:8px 0 4px 18px;padding:0;color:#334155;">
        <li>How archetype-similar patients were treated at this same
            decision point.</li>
        <li>Functional-outcome rates among those similar patients,
            broken out by treatment.</li>
      </ul>
      This is a descriptive evidence summary, not a recommendation.
    </div>
    """,
    unsafe_allow_html=True,
)

# ── "Most common treatment" descriptive card ──────────────────────────────
st.markdown(
    f"""
    <div style="border:1px solid #e2e8f0;border-radius:10px;
                padding:14px 16px;background:#fff;margin-bottom:12px;">
      <div style="font-size:12.5px;text-transform:uppercase;
                  letter-spacing:0.08em;color:#475569;font-weight:700;">
        Most common treatment among similar patients at L{sel_level}
      </div>
      <div style="font-size:1.05rem;font-weight:700;color:#0f172a;
                  margin:5px 0 3px 0;">
        {ACTION_LABELS[practice]}
      </div>
      <div style="font-size:12.5px;color:#475569;">
        {freq[practice]:.0%} of the {prac['n_total']} similar patients at
        this stage. Clinician's observed choice for this patient:
        <b>{ACTION_LABELS[obs]}</b>.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

p_obs = p_by_action.get(obs)
sc1, sc2 = st.columns(2)
for col, label, value in [
    (sc1, "Functional rate — observed treatment",
     f"{p_obs:.0%}" if p_obs is not None else "no support"),
    (sc2, "Similar patients at this stage", f"{prac['n_total']}"),
]:
    with col:
        st.markdown(
            f"<div class='stat-card'><p class='stat-card-label'>{label}</p>"
            f"<p class='stat-card-value'>{value}</p></div>",
            unsafe_allow_html=True,
        )

# ── Two descriptive charts (no "optimal" labeling) ────────────────────────
st.markdown(
    "<p class='section-label'>How similar patients were treated, "
    "and their outcomes</p>",
    unsafe_allow_html=True,
)
ch_l, ch_r = st.columns(2)

with ch_l:
    acts = [a for a in ACTIONS if p_by_action.get(a) is not None]
    fig1 = go.Figure(go.Bar(
        x=[ACTION_LABELS[a] for a in acts],
        y=[p_by_action[a] for a in acts],
        marker_color=[ACTION_COLORS[a] for a in acts],
        text=[f"{p_by_action[a]:.0%}" for a in acts],
        textposition="outside",
    ))
    fig1.update_layout(
        title=dict(text="Functional outcome rate by treatment "
                   "(similar patients)", font=dict(size=12.5)),
        yaxis=dict(range=[0, 1.15], tickformat=".0%", gridcolor="#f1f5f9"),
        xaxis=dict(showgrid=False),
        height=270, margin=dict(t=42, b=20, l=10, r=10),
        plot_bgcolor="white", paper_bgcolor="white", showlegend=False,
    )
    st.plotly_chart(fig1, use_container_width=True)
    st.caption("Similarity-weighted functional-outcome rate among "
               "level-matched patients who took each treatment.")

with ch_r:
    fa = list(ACTIONS)
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
               "each treatment — observed practice, independent of outcome.")

# ── Similar patients list ─────────────────────────────────────────────────
st.markdown("<p class='section-label'>Similar historical patients</p>",
            unsafe_allow_html=True)
similar = retrieve_similar(patient, train, TOP_K_SIMILAR)
st.markdown(
    f"<div class='info-line'>The above panels are grounded in the "
    f"<b>{len(similar)} most archetype-similar</b> historical patients, "
    f"each weighted by closeness.</div>",
    unsafe_allow_html=True,
)
for rank, item in enumerate(similar, 1):
    tp = item["record"]
    lvl = sel_level if sel_level in tp["levels"] else tp["max_level"]
    tli = tp["levels"][lvl]
    out = tp["outcome"]["functional_status"]
    oc = "#16a34a" if out == "functional" else (
        "#ea580c" if out == "impaired" else "#64748b")
    st.markdown(
        f"""
        <div style='display:flex;align-items:center;gap:14px;
                    padding:8px 12px;border:1px solid #e2e8f0;
                    border-radius:8px;margin-bottom:6px;'>
          <div style='flex:0 0 26px;font-weight:700;color:#2563eb;'>#{rank}</div>
          <div style='flex:1;font-size:13.5px;'>{tp['headline']}</div>
          <div style='flex:0 0 130px;font-size:12.5px;color:#475569;'>
            L{lvl}: {ACTION_LABELS[tli['action']]}</div>
          <div style='flex:0 0 90px;font-size:12.5px;font-weight:600;
                      color:{oc};'>{out.title()}</div>
          <div style='flex:0 0 80px;font-size:11.5px;color:#64748b;
                      text-align:right;'>sim {item['similarity']:.2f}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Reconstructed clinical note (provenance) ──────────────────────────────
st.markdown("<p class='section-label'>Clinical pathway (up to this level)</p>",
            unsafe_allow_html=True)
note = reconstruct_note(patient, sel_level)
st.markdown(
    f"<div style='font-size:13px;line-height:1.7;color:#334155;"
    f"max-height:300px;overflow-y:auto;background:#f8fafc;padding:12px 14px;"
    f"border-radius:6px;border:1px solid #e2e8f0;'>"
    f"{note.replace(chr(10), '<br/>')}</div>",
    unsafe_allow_html=True,
)

# ── Patient data-quality flags (provenance) ───────────────────────────────
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
        f"extraction step. They are shown so the evidence above is read "
        f"in light of the underlying note quality.</div>",
        unsafe_allow_html=True,
    )

# ── Observed outcome (audit / evaluation) ─────────────────────────────────
with st.expander("Reveal observed outcome (for evaluation only)",
                 expanded=False):
    out = patient["outcome"]
    st.markdown(
        f"This patient's recorded functional status at last follow-up was "
        f"**{out['functional_status']}** "
        f"(ECOG {out['ecog_score']}, KPS {out['kps_score']}). "
        f"Use this to audit the evidence summary against the observed "
        f"outcome."
    )

style.footer()
