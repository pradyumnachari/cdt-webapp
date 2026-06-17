"""Similar patients & evidence — retrospective per-patient evidence panel.

Pick a held-out patient and a decision level. The page shows what the
patient actually received at that decision point, what historical
archetype-similar patients chose at the same point, and how they did.
The page is descriptive evidence — no recommendation, no "optimal
action", no counterfactual analysis.
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
from lib.engine import counterfactuals, retrieve_similar  # noqa: E402

st.set_page_config(page_title="Similar patients & evidence — Ask my data",
                   page_icon="🧠", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    </style>
""", unsafe_allow_html=True)
style.inject()
nav.render("similar")

cohort = get_cohort()
patients = cohort["patients"]
train = cohort["train"]
test = cohort["test"]

# Held-out only — that is the only mode for this page.
pool = test if test else patients


# ── Auto-pick illustrative cases (neutral tags, no "model agrees") ────────
@st.cache_data(show_spinner="Selecting illustrative cases…")
def pick_exemplars() -> list:
    """Choose up to 5 patients that each tell a different descriptive story.

    Tags are neutral (no prescriptive language). ΔU from `counterfactuals`
    is used as a *signal of how distinct a case is*, NOT as a recommendation.
    """
    scored = []
    src_pool = test if test else patients
    for pid, rec in src_pool.items():
        try:
            cfs = counterfactuals(rec, train)
        except Exception:  # noqa: BLE001
            continue
        total_du = sum(c["delta_u"] for c in cfs)
        best_level = max(cfs, key=lambda c: c["delta_u"])["level"] if cfs else 1
        scored.append({
            "pid": pid, "rec": rec, "total_du": total_du,
            "best_level": best_level, "n_cf": len(cfs),
            "n_levels": len(rec.get("levels") or {}),
            "age": rec["demographics"].get("age") or 0,
            "grade": rec["stratification"]["grade"],
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
         "Notable treatment / outcome contrast",
         "#7c3aed",
         "The observed trajectory looks different from what archetype-"
         "similar patients with the best functional outcomes received.")

    g23 = [s for s in scored if s["grade"] in ("grade_2", "grade_3")]
    if g23:
        take(max(g23, key=lambda s: s["total_du"]),
             "Higher-grade tumour", "#0891b2",
             "Atypical or anaplastic tumour — a harder, higher-risk case.")

    young = sorted([s for s in scored if s["age"] > 0],
                   key=lambda s: s["age"])
    if young:
        take(young[0], "Younger patient", "#d97706",
             "Long horizon weighs on the watch-vs-treat call.")

    older = sorted([s for s in scored if s["age"] > 0],
                   key=lambda s: -s["age"])
    if older:
        take(older[0], "Older patient", "#b91c1c",
             "Comorbidity and recovery risk become more important here.")

    multi = sorted([s for s in scored if s["n_levels"] >= 3],
                   key=lambda s: -s["total_du"])
    if multi:
        take(multi[0], "Multi-step pathway", "#0369a1",
             "Reached three decision points — a longer trajectory with "
             "more chances to inspect the evidence.")

    return chosen[:5]


# ─────────────────────────────────────────────────────────────────────────
# Hero
# ─────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero" style="padding:24px 4px 14px 4px;">
      <p class="hero-eyebrow">Similar patients &amp; evidence</p>
      <h1 class="hero-title" style="font-size:1.85rem;">
        For one patient at one decision point, see how archetype-similar
        patients were treated and how they did.</h1>
      <p class="hero-sub">
        Pick a patient and one of their <b>decision levels</b>, then read
        the descriptive evidence below — what the patient actually
        received, what similar historical patients chose at the same
        point, and how they did. This page is a retrospective summary,
        not a recommendation.
      </p>
      <div style="font-size:13px;color:#475569;margin-top:8px;
                  line-height:1.55;">
        <b>What is a decision level?</b> Each patient's pathway is
        divided into sequential decision points. <b>L1</b> is the first
        treatment decision after diagnosis; <b>L2</b> is the next
        decision (recurrence, growth on imaging, new symptoms);
        <b>L3</b> is a third decision if the patient reaches one. Many
        patients never do. Consecutive same-action events (e.g. years of
        stable surveillance) are collapsed into one level.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


def _select(pid: str, level: int) -> None:
    st.session_state["selected_pid"] = pid
    st.session_state["selected_level"] = level
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────
# Illustrative cases
# ─────────────────────────────────────────────────────────────────────────
exemplars = pick_exemplars()
if exemplars:
    st.markdown("<p class='section-label'>Illustrative cases</p>",
                unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:13.5px;color:#334155;line-height:1.55;"
        "margin:0 0 12px 0;'>"
        "A few held-out patients chosen to span different clinical "
        "profiles — useful starting points if you don't have a specific "
        "patient in mind. Click <i>Open patient</i> on any tile to load "
        "the evidence panels for that case below."
        "</div>",
        unsafe_allow_html=True,
    )
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


# ─────────────────────────────────────────────────────────────────────────
# Patient picker (held-out only)
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label'>Pick a held-out patient</p>",
            unsafe_allow_html=True)
default_pid = st.session_state.get("selected_pid") or next(iter(pool))
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

# ─────────────────────────────────────────────────────────────────────────
# Patient header + state strip + level selector
# ─────────────────────────────────────────────────────────────────────────
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
        help=("L1 = first treatment decision after diagnosis. "
              "L2 = next decision. L3 = third decision if reached. "
              "Pick the level you want to inspect."),
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

# ─────────────────────────────────────────────────────────────────────────
# Compute the descriptive evidence from the SIMILAR patients only.
# (Earlier versions reported a denominator of N=~200 by pulling
# `practice_recommendation`'s `n_total`, which counts *every* training
# patient who reached the level, similarity-weighted. The denominator
# was technically right but clinically misleading — most of those
# patients have near-zero archetype similarity. The honest summary
# restricts to the top-K most archetype-similar patients who actually
# reached this level, and weights them equally.)
# ─────────────────────────────────────────────────────────────────────────

K_SUMMARY = 20  # target size of the "similar patients" subset

# Cast a wider net than K_SUMMARY because some of the top candidates may
# not have reached this decision level.
_candidates = retrieve_similar(patient, train, K_SUMMARY * 6)
similar_at_level = [c for c in _candidates
                    if sel_level in c["record"]["levels"]][:K_SUMMARY]
n_similar = len(similar_at_level)

obs = patient["levels"][sel_level]["action"]

# Treatment shares + outcome rates from the similar-at-level subset
_count_by_action: dict = {a: 0 for a in ACTIONS}
_outcome_by_action: dict = {a: {"functional": 0, "impaired": 0, "unknown": 0}
                            for a in ACTIONS}
for _item in similar_at_level:
    _rec = _item["record"]
    _a = _rec["levels"][sel_level]["action"]
    _count_by_action.setdefault(_a, 0)
    _count_by_action[_a] += 1
    _out = _rec["outcome"]["functional_status"]
    _outcome_by_action.setdefault(
        _a, {"functional": 0, "impaired": 0, "unknown": 0})
    _outcome_by_action[_a][_out] = _outcome_by_action[_a].get(_out, 0) + 1

freq: dict = {a: ((_count_by_action[a] / n_similar) if n_similar else 0)
              for a in ACTIONS}
p_by_action: dict = {}
for _a in ACTIONS:
    _nf = _outcome_by_action[_a]["functional"]
    _ni = _outcome_by_action[_a]["impaired"]
    _nk = _nf + _ni
    p_by_action[_a] = (_nf / _nk) if _nk else None

# Most common treatment in the subset (descriptive; not a recommendation)
practice = (max(ACTIONS, key=lambda a: _count_by_action.get(a, 0))
            if n_similar else obs)

# ─────────────────────────────────────────────────────────────────────────
# "How to read this view" — short, practical, level-specific
# ─────────────────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <div class="info-line" style="font-size:13.5px;line-height:1.6;">
      <b>At decision L{sel_level}, this patient actually received
      <span style="color:#0f172a;">{ACTION_LABELS[obs]}</span>.</b>
      The panels below answer two questions about archetype-similar
      historical patients who reached the same decision point:
      <ul style="margin:8px 0 6px 18px;padding:0;color:#334155;">
        <li><b>What did they choose at this decision point?</b> — the
            most common treatments among the similar subset.</li>
        <li><b>How did each treatment do at last follow-up?</b> — we
            take all similar patients who chose a given treatment at
            this decision point, then look at their <i>final, long-term
            functional status</i> recorded later in their charts, and
            report the share of them who remained functional.</li>
      </ul>
      <div style="margin-top:8px;padding:8px 10px;background:#fff;
                  border-radius:4px;border:1px solid #fcd34d;
                  font-size:13px;color:#334155;">
        <b>Functional rate</b> = the fraction of patients whose last
        recorded performance status (ECOG / KPS) was independent —
        specifically ECOG&nbsp;0–2 or KPS&nbsp;≥&nbsp;70. It captures
        long-term outcome <i>after</i> the chosen treatment played out,
        not the immediate post-treatment state.
      </div>
      <div style="margin-top:8px;color:#475569;font-size:13px;">
        This is descriptive evidence, not a recommendation.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%" if x is not None else "—"


# Build the natural-language summary the user reads first
acts_ordered = sorted(
    [a for a in ACTIONS if freq.get(a, 0) > 0],
    key=lambda a: -freq[a],
)
choice_phrases = [
    f"<b>{_pct(freq[a])}</b> received <b>{ACTION_LABELS[a]}</b> "
    f"(n={_count_by_action.get(a, 0)})"
    for a in acts_ordered
]
acts_with_rate = [a for a in ACTIONS if p_by_action.get(a) is not None]
outcome_phrases = [
    f"<b>{ACTION_LABELS[a]}</b>: {_pct(p_by_action[a])}"
    for a in acts_with_rate
]
p_obs = p_by_action.get(obs)
obs_rate_phrase = (f"the functional-outcome rate associated with the "
                   f"<b>{ACTION_LABELS[obs]}</b> chosen for this "
                   f"patient is <b>{_pct(p_obs)}</b>.")

st.markdown(
    f"""
    <div style="border:1px solid #e2e8f0;border-radius:10px;
                padding:16px 18px;background:#fff;margin-bottom:12px;
                font-size:14px;color:#0f172a;line-height:1.65;">
      <div style="font-size:12.5px;text-transform:uppercase;
                  letter-spacing:0.08em;color:#475569;font-weight:700;
                  margin-bottom:8px;">
        Summary at L{sel_level}
      </div>
      Among the <b>{n_similar}</b> most archetype-similar historical
      patients who reached this decision level (top
      {K_SUMMARY}, equally weighted within the subset):<br/>
      &nbsp;&nbsp;• {' &nbsp;·&nbsp; '.join(choice_phrases)}.
      <br/>
      The most common choice was <b>{ACTION_LABELS[practice]}</b>;
      the clinician's choice for this patient was
      <b>{ACTION_LABELS[obs]}</b>.<br/><br/>
      <b>By treatment, the functional-outcome rate was</b><br/>
      &nbsp;&nbsp;• {' &nbsp;·&nbsp; '.join(outcome_phrases)}.
      <br/><br/>
      In particular, {obs_rate_phrase}
    </div>
    """,
    unsafe_allow_html=True,
)

# Optional charts (off by default — the text above is the primary view)

# "How are similar patients calculated?" — on-demand, info-only
with st.expander("How are similar patients calculated?", expanded=False):
    st.markdown(
        f"""
        **Matching is done on archetype** — the combination of WHO grade,
        tumour location, age band, and gender. Every historical
        training patient is scored against this index patient on those
        four dimensions and given a *similarity weight* between 0 and 1.

        For the **summary above**, we take the **top
        {K_SUMMARY} most archetype-similar patients who also reached
        decision level L{sel_level}** ({n_similar} found for this
        patient), and weight them equally inside that subset. We
        deliberately *do not* dilute the average by including patients
        whose archetype barely overlaps with this one. The summary
        denominator is the count of that similar subset, not the count
        of everyone at this level.

        The list of *similar historical patients* below shows the top
        {TOP_K_SIMILAR} of those — the named patients you can read
        individually, each with their archetype-similarity score.
        """
    )
with st.expander(f"Show bar charts: how similar patients were treated at L{sel_level} and their functional outcomes", expanded=False):
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
            yaxis=dict(range=[0, 1.15], tickformat=".0%",
                       gridcolor="#f1f5f9"),
            xaxis=dict(showgrid=False),
            height=270, margin=dict(t=42, b=20, l=10, r=10),
            plot_bgcolor="white", paper_bgcolor="white",
            showlegend=False,
        )
        st.plotly_chart(fig1, use_container_width=True)
    with ch_r:
        fa = list(ACTIONS)
        fig2 = go.Figure(go.Bar(
            x=[ACTION_LABELS[a] for a in fa],
            y=[freq[a] for a in fa],
            marker_color=[ACTION_COLORS[a] for a in fa],
            text=[f"{freq[a]:.0%}<br>(n={_count_by_action.get(a, 0)})"
                  for a in fa],
            textposition="outside",
        ))
        fig2.update_layout(
            title=dict(text="What similar patients chose at this stage",
                       font=dict(size=12.5)),
            yaxis=dict(range=[0, 1.18], tickformat=".0%",
                       gridcolor="#f1f5f9"),
            xaxis=dict(showgrid=False),
            height=270, margin=dict(t=42, b=20, l=10, r=10),
            plot_bgcolor="white", paper_bgcolor="white",
            showlegend=False,
        )
        st.plotly_chart(fig2, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────
# What actually happened to this patient (moved up from page bottom)
# ─────────────────────────────────────────────────────────────────────────
with st.expander("What actually happened to this patient at last follow-up?",
                 expanded=False):
    out = patient["outcome"]
    out_color = ("#16a34a" if out["functional_status"] == "functional"
                 else "#ea580c" if out["functional_status"] == "impaired"
                 else "#64748b")
    st.markdown(
        f"<div style='font-size:14px;line-height:1.6;color:#0f172a;'>"
        f"At last recorded follow-up, this patient's functional status "
        f"was "
        f"<b style='color:{out_color};'>{out['functional_status']}</b> "
        f"(ECOG {out['ecog_score']}, KPS {out['kps_score']}). Use this "
        f"to audit the evidence above against the observed outcome. "
        f"The model never sees this value when computing the panels."
        f"</div>",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────
# Similar historical patients list
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label'>Similar historical patients</p>",
            unsafe_allow_html=True)
similar = similar_at_level[:TOP_K_SIMILAR]
st.markdown(
    f"<div class='info-line'>Each row below is one of the top "
    f"<b>{len(similar)}</b> most archetype-similar historical patients "
    f"who reached this same decision level — a sample drawn from the "
    f"{n_similar}-patient subset that fed the summary above. The "
    f"rightmost number is each patient's archetype-similarity score to "
    f"this patient.</div>",
    unsafe_allow_html=True,
)
for rank, item in enumerate(similar, 1):
    tp = item["record"]
    lvl = sel_level if sel_level in tp["levels"] else tp["max_level"]
    tli = tp["levels"][lvl]
    out = tp["outcome"]["functional_status"]
    oc = ("#16a34a" if out == "functional"
          else ("#ea580c" if out == "impaired" else "#64748b"))
    st.markdown(
        f"""
        <div style='display:flex;align-items:center;gap:14px;
                    padding:8px 12px;border:1px solid #e2e8f0;
                    border-radius:8px;margin-bottom:6px;'>
          <div style='flex:0 0 26px;font-weight:700;color:#2563eb;'>
            #{rank}</div>
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

# ─────────────────────────────────────────────────────────────────────────
# Clinical pathway (with explanation)
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label'>Clinical pathway (up to this level)</p>",
            unsafe_allow_html=True)
st.markdown(
    "<div style='font-size:13.5px;color:#334155;line-height:1.6;"
    "margin:0 0 10px 0;'>"
    "Below is a structured summary of this patient's clinical history "
    "up to the selected decision level, reconstructed from their "
    "longitudinal notes. Each line is one extracted clinical event "
    "— an imaging study, a surgery, a radiation course, a clinic visit "
    "— pulled from the unstructured notes by the extraction pipeline. "
    "Use this as a quick read of the underlying chart, so you can see "
    "what the descriptive evidence above is grounded in."
    "</div>",
    unsafe_allow_html=True,
)
note = reconstruct_note(patient, sel_level)
st.markdown(
    f"<div style='font-size:13px;line-height:1.7;color:#334155;"
    f"max-height:300px;overflow-y:auto;background:#f8fafc;padding:12px 14px;"
    f"border-radius:6px;border:1px solid #e2e8f0;'>"
    f"{note.replace(chr(10), '<br/>')}</div>",
    unsafe_allow_html=True,
)

style.footer()
