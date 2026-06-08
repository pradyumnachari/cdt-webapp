"""Try it — pick a patient (auto-selected exemplars or full list)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import nav, style                        # noqa: E402
from lib.bootstrap import get_cohort               # noqa: E402
from lib.buckets import ACTION_LABELS              # noqa: E402
from lib.engine import counterfactuals             # noqa: E402

st.set_page_config(page_title="Try it — CDT", page_icon="🧠",
                   layout="wide", initial_sidebar_state="collapsed")
style.inject()
nav.render("try")

cohort = get_cohort()
patients = cohort["patients"]
train = cohort["train"]
test = cohort["test"]


# ── Auto-select exemplars (works for any dataset, no hardcoded IDs) ────────
@st.cache_data(show_spinner="Selecting illustrative cases…")
def pick_exemplars() -> list:
    """Choose a few patients that each tell a different story."""
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
    take(by_du[0], "Model disagrees", "#dc2626",
         "Largest gap between the observed pathway and the model's "
         "preferred actions.")
    take(by_du[-1], "Model agrees", "#16a34a",
         "Observed pathway closely matches the model's recommendations.")

    g23 = [s for s in scored
           if s["rec"]["stratification"]["grade"] in ("grade_2", "grade_3")]
    if g23:
        take(max(g23, key=lambda s: s["total_du"]), "Higher grade", "#7c3aed",
             "Atypical or anaplastic tumour — a harder, higher-risk case.")

    young = sorted(scored,
                   key=lambda s: s["rec"]["demographics"].get("age") or 999)
    take(young[0], "Younger patient", "#d97706",
         "Young patient — long horizon weighs on the watch-vs-treat call.")

    return chosen[:4]


# ── Hero ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero" style="padding:30px 4px 16px 4px;">
      <p class="hero-eyebrow">Try it</p>
      <h1 class="hero-title" style="font-size:1.9rem;">
        Pick a patient to see the recommendation.</h1>
      <p class="hero-sub">Start with an illustrative case below, or choose
      any patient from the full list.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def _go(pid: str, level: int) -> None:
    st.session_state["selected_pid"] = pid
    st.session_state["selected_level"] = level
    st.switch_page("pages/2_Recommendation.py")


# ── Exemplar tiles ─────────────────────────────────────────────────────────
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
                _go(ex["pid"], ex["best_level"])

# ── Full patient picker ────────────────────────────────────────────────────
st.markdown("<p class='section-label'>All patients</p>",
            unsafe_allow_html=True)

split_choice = st.radio(
    "Cohort", ["Held-out patients", "All patients"],
    horizontal=True, label_visibility="collapsed",
)
pool = test if (split_choice == "Held-out patients" and test) else patients

options = sorted(pool.keys())
pid = st.selectbox(
    "Patient",
    options,
    format_func=lambda p: f"{pool[p]['display_id']} — {pool[p]['headline']}",
)
rec = pool[pid]

c1, c2 = st.columns([2, 1])
with c1:
    levels = sorted(rec["levels"])
    level = st.selectbox(
        "Decision level",
        levels,
        format_func=lambda L: (
            f"Level {L} — {rec['levels'][L]['state_key']} · observed: "
            f"{ACTION_LABELS[rec['levels'][L]['action']]}"
        ),
    )
with c2:
    st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
    if st.button("See recommendation", type="primary",
                 use_container_width=True):
        _go(pid, level)

style.footer()
