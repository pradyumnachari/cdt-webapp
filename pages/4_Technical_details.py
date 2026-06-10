"""Technical details — concise companion to the clinician-facing
Overview. Not in the top nav; reached only via the link at the bottom
of the Overview page.

Distils what is novel about the framework and why it could not be
done with prior approaches. Based on the team's two papers
(MICCAI: Stratified Trajectory Tree + Contextual Power Priors;
COLM: Cohort-to-Text generation with the locked-stats-block firewall)
and reflects the current implementation in this webapp.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import nav, style  # noqa: E402

st.set_page_config(
    page_title="Technical details — Ask my data",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)
style.inject()
nav.render("overview")


# ─────────────────────────────────────────────────────────────────────────
# Header + back link
# ─────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero" style="padding:18px 4px 10px 4px;">
      <p class="hero-eyebrow">Technical details</p>
      <h1 class="hero-title" style="font-size:1.75rem;">
        How Ask my data works, and why it could not be done before.</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

back_l, _ = st.columns([1, 5])
with back_l:
    if st.button("← Back to Overview", use_container_width=True):
        st.switch_page("app.py")


# ─────────────────────────────────────────────────────────────────────────
# 1. The problem
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label' style='margin-top:24px;'>"
            "1. The problem</p>",
            unsafe_allow_html=True)
st.markdown(
    """
    - **Sparsity across patients.** Stratifying a few-hundred-patient
      registry by grade × location × age × sex leaves many subgroups
      with a handful of cases each.
    - **Noise inside each patient.** Years of free-text notes per
      person; the decisive information is buried in prose.

    Existing tools address one or the other. None handles both
    together while producing a queryable structure clinicians can
    interact with.
    """
)


# ─────────────────────────────────────────────────────────────────────────
# 2. End-to-end pipeline
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label' style='margin-top:24px;'>"
            "2. The framework, end to end</p>",
            unsafe_allow_html=True)

PIPELINE_HTML = (
    "<div style='display:grid;grid-template-columns:1fr 1.2fr 1fr;"
    "gap:18px;margin:8px 0;'>"
    "<div style='border:1px solid #e2e8f0;border-radius:10px;"
    "background:#f8fafc;padding:14px 16px;'>"
    "<div style='font-size:11.5px;text-transform:uppercase;"
    "letter-spacing:0.10em;font-weight:700;color:#475569;'>Input</div>"
    "<div style='font-size:15px;font-weight:700;color:#0f172a;"
    "margin:4px 0 6px 0;'>Unstructured longitudinal notes</div>"
    "<div style='font-size:13px;color:#334155;line-height:1.5;'>"
    "Many notes per patient. Free text.</div></div>"
    "<div style='border:2px solid #2563eb;border-radius:10px;"
    "background:#eff6ff;padding:14px 16px;'>"
    "<div style='font-size:11.5px;text-transform:uppercase;"
    "letter-spacing:0.10em;font-weight:700;color:#1d4ed8;'>Substrate</div>"
    "<div style='font-size:15px;font-weight:700;color:#0f172a;"
    "margin:4px 0 6px 0;'>Stratified Trajectory Tree (STT)</div>"
    "<div style='font-size:13px;color:#334155;line-height:1.5;'>"
    "Records indexed by archetype, level, state, action — with "
    "Contextual Power Priors borrowing across sparse cells.</div></div>"
    "<div style='border:1px solid #e2e8f0;border-radius:10px;"
    "background:#f8fafc;padding:14px 16px;'>"
    "<div style='font-size:11.5px;text-transform:uppercase;"
    "letter-spacing:0.10em;font-weight:700;color:#475569;'>Outputs</div>"
    "<div style='font-size:15px;font-weight:700;color:#0f172a;"
    "margin:4px 0 6px 0;'>Four uses, one structure</div>"
    "<div style='font-size:13px;color:#334155;line-height:1.5;'>"
    "Cohort Q&amp;A · per-patient evidence · action-conditioned "
    "outcomes · pathway summaries.</div></div></div>"
)
st.markdown(PIPELINE_HTML, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────
# 3. STT
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label' style='margin-top:24px;'>"
            "3. Stratified Trajectory Tree</p>",
            unsafe_allow_html=True)
st.markdown(
    "Patients are grouped into **cells** by their archetype (grade × "
    "location × age × sex). Each cell holds every patient with that "
    "exact profile, indexed by decision level and the action they "
    "took. The colour beside each patient below shows which cell they "
    "land in."
)


def _patient_tag(label: str, color: str) -> str:
    """Coloured dot tag identifying which cell a patient belongs to."""
    return (
        f"<span style='display:inline-block;width:10px;height:10px;"
        f"background:{color};border-radius:2px;margin-right:8px;"
        f"vertical-align:middle;'></span>{label}"
    )


# Patient → cell mapping: A,D → blue cell; B → green; C → orange
_BLUE = "#2563eb"      # cell 1
_GREEN = "#16a34a"     # cell 2
_ORANGE = "#ea580c"    # cell 3


STT_HTML = (
    "<div style='border:1px solid #e2e8f0;border-radius:10px;"
    "background:#f8fafc;padding:16px 18px;margin:10px 0;'>"
    # Header row
    "<div style='display:grid;grid-template-columns:1.2fr 1.8fr;"
    "gap:24px;'>"
    "<div style='font-size:12px;text-transform:uppercase;"
    "letter-spacing:0.10em;font-weight:700;color:#475569;'>"
    "Patients (varied attributes)</div>"
    "<div style='font-size:12px;text-transform:uppercase;"
    "letter-spacing:0.10em;font-weight:700;color:#475569;'>"
    "Stratified into cells by archetype</div>"
    "</div>"

    # Body row: patient list on left, three cells on right
    "<div style='display:grid;grid-template-columns:1.2fr 1.8fr;"
    "gap:24px;margin-top:8px;align-items:start;'>"

    # ── LEFT: patients with colour tags ──
    f"<div style='font-size:13px;color:#334155;line-height:2;'>"
    f"{_patient_tag('Patient A · grade 1 · skull base · 55 yr · F', _BLUE)}<br/>"
    f"{_patient_tag('Patient B · grade 1 · convexity · 42 yr · M', _GREEN)}<br/>"
    f"{_patient_tag('Patient C · grade 2 · parasagittal · 67 yr · F', _ORANGE)}<br/>"
    f"{_patient_tag('Patient D · grade 1 · skull base · 60 yr · F', _BLUE)}<br/>"
    f"<span style='color:#94a3b8;margin-left:18px;'>…</span></div>"

    # ── RIGHT: three cells ──
    "<div>"

    # Cell 1 (BLUE)
    f"<div style='border:1px solid {_BLUE}55;border-left:4px solid {_BLUE};"
    "border-radius:6px;background:white;padding:10px 12px;margin-bottom:8px;'>"
    f"<div style='font-size:12.5px;font-weight:700;color:#0f172a;'>"
    f"<span style='display:inline-block;width:10px;height:10px;"
    f"background:{_BLUE};border-radius:2px;margin-right:8px;'></span>"
    "Cell · grade 1 · skull base · 50–65 · F</div>"
    "<div style='font-size:12px;color:#475569;margin-top:3px;'>"
    "Contains: <b>Patient A, Patient D</b></div>"
    "<div style='font-size:11.5px;color:#0f172a;margin-top:5px;"
    "display:flex;gap:6px;flex-wrap:wrap;'>"
    "<span style='background:#bbf7d0;padding:2px 8px;border-radius:4px;'>"
    "L1 · Watch &amp; Wait</span>"
    "<span style='background:#bbf7d0;padding:2px 8px;border-radius:4px;'>"
    "L2 · Watch &amp; Wait</span>"
    "</div></div>"

    # Cell 2 (GREEN)
    f"<div style='border:1px solid {_GREEN}55;border-left:4px solid {_GREEN};"
    "border-radius:6px;background:white;padding:10px 12px;margin-bottom:8px;'>"
    f"<div style='font-size:12.5px;font-weight:700;color:#0f172a;'>"
    f"<span style='display:inline-block;width:10px;height:10px;"
    f"background:{_GREEN};border-radius:2px;margin-right:8px;'></span>"
    "Cell · grade 1 · convexity · &lt; 50 · M</div>"
    "<div style='font-size:12px;color:#475569;margin-top:3px;'>"
    "Contains: <b>Patient B</b></div>"
    "<div style='font-size:11.5px;color:#0f172a;margin-top:5px;"
    "display:flex;gap:6px;flex-wrap:wrap;'>"
    "<span style='background:#ddd6fe;padding:2px 8px;border-radius:4px;'>"
    "L1 · Surgery</span>"
    "</div></div>"

    # Cell 3 (ORANGE)
    f"<div style='border:1px solid {_ORANGE}55;border-left:4px solid {_ORANGE};"
    "border-radius:6px;background:white;padding:10px 12px;'>"
    f"<div style='font-size:12.5px;font-weight:700;color:#0f172a;'>"
    f"<span style='display:inline-block;width:10px;height:10px;"
    f"background:{_ORANGE};border-radius:2px;margin-right:8px;'></span>"
    "Cell · grade 2 · parasagittal · &gt; 65 · F</div>"
    "<div style='font-size:12px;color:#475569;margin-top:3px;'>"
    "Contains: <b>Patient C</b></div>"
    "<div style='font-size:11.5px;color:#0f172a;margin-top:5px;"
    "display:flex;gap:6px;flex-wrap:wrap;'>"
    "<span style='background:#ddd6fe;padding:2px 8px;border-radius:4px;'>"
    "L1 · Surgery</span>"
    "<span style='background:#fecaca;padding:2px 8px;border-radius:4px;'>"
    "L2 · Radiation</span>"
    "</div></div>"

    "</div></div></div>"
)
st.markdown(STT_HTML, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────
# 4. CPP — borrowing diagram
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label' style='margin-top:24px;'>"
            "4. Contextual Power Priors: sparsity fix</p>",
            unsafe_allow_html=True)
st.markdown(
    "Most cells are sparse. CPP borrows evidence from neighbouring "
    "cells, weighted by how similar each neighbour's archetype is."
)


def _cpp_row(diff: str, archetype: str, n: int, weight: float) -> str:
    if weight >= 0.65:
        bar_color = "#16a34a"
    elif weight >= 0.40:
        bar_color = "#ca8a04"
    else:
        bar_color = "#dc2626"
    pct = int(weight * 100)
    return (
        "<div style='display:grid;grid-template-columns:"
        "1.1fr 1.6fr 0.5fr 1.4fr;gap:14px;align-items:center;"
        "padding:8px 10px;border:1px solid #e2e8f0;border-radius:6px;"
        "background:white;margin-bottom:6px;'>"
        f"<div style='font-size:12px;color:#475569;'>"
        f"<i>differs only by</i><br/>"
        f"<b style='color:#0f172a;'>{diff}</b></div>"
        f"<div style='font-size:12.5px;color:#0f172a;'>{archetype}</div>"
        f"<div style='font-size:12px;color:#475569;text-align:right;'>"
        f"n = {n}</div>"
        "<div>"
        "<div style='height:8px;background:#e2e8f0;border-radius:4px;"
        "overflow:hidden;'>"
        f"<div style='width:{pct}%;height:100%;background:{bar_color};'>"
        "</div></div>"
        f"<div style='font-size:11.5px;color:{bar_color};"
        f"font-weight:700;margin-top:3px;'>weight {weight:.2f}</div>"
        "</div></div>"
    )

CPP_HTML = (
    "<div style='border:1px solid #e2e8f0;border-radius:10px;"
    "background:#f8fafc;padding:16px 18px;margin:10px 0;'>"
    "<div style='font-size:11.5px;text-transform:uppercase;"
    "letter-spacing:0.10em;font-weight:700;color:#1d4ed8;"
    "margin-bottom:6px;'>Target cell · sparse</div>"
    "<div style='border:2px solid #2563eb;border-radius:8px;"
    "padding:12px 14px;background:#eff6ff;margin-bottom:12px;'>"
    "<div style='font-size:14px;font-weight:700;color:#0f172a;'>"
    "grade 2 · parasagittal · &gt; 65 · F"
    "</div>"
    "<div style='font-size:12.5px;color:#475569;margin-top:3px;'>"
    "Only <b style='color:#dc2626;'>n = 3</b> patients — too few on "
    "their own.</div></div>"
    "<div style='font-size:11.5px;text-transform:uppercase;"
    "letter-spacing:0.10em;font-weight:700;color:#475569;"
    "margin:0 0 6px 0;'>Neighbours contribute, weighted by similarity"
    "</div>"
    + _cpp_row("age band", "grade 2 · parasagittal · 50–65 · F",
               n=7, weight=0.78)
    + _cpp_row("sex", "grade 2 · parasagittal · &gt; 65 · M",
               n=4, weight=0.55)
    + _cpp_row("location", "grade 2 · convexity · &gt; 65 · F",
               n=5, weight=0.42)
    + _cpp_row("grade", "grade 1 · parasagittal · &gt; 65 · F",
               n=12, weight=0.18)
    + "</div>"
)
st.markdown(CPP_HTML, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────
# 5. Q&A: separating compute from narrate
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label' style='margin-top:24px;'>"
            "5. Q&amp;A: separating compute from narrate</p>",
            unsafe_allow_html=True)
st.markdown(
    "A language model given the cohort directly tends to **invent "
    "aggregate numbers**, **conflate facts across patients**, and "
    "**lose time anchors** — because it has no built-in mechanism to "
    "compute population-level statistics, only to write plausible-"
    "sounding prose around the individual records it attends to."
)

st.markdown(
    "Our fix is **strict separation**: the language model is never "
    "asked to do arithmetic. Statistics are computed in code, sealed, "
    "and only then narrated. Every number in the prose is checked "
    "against the sealed block."
)


def _cca_stage(badge_color: str, badge: str, name: str, body: str,
               highlight: bool = False) -> str:
    border = "2px solid #f59e0b" if highlight else "1px solid #cbd5e1"
    bg = "#fffbeb" if highlight else ("#eff6ff" if badge_color == "#1d4ed8"
                                       else "white")
    return (
        f"<div style='border:{border};border-radius:6px;"
        f"padding:10px 12px;background:{bg};'>"
        f"<div style='font-size:11px;font-weight:700;color:{badge_color};"
        f"text-transform:uppercase;letter-spacing:0.10em;'>{badge}</div>"
        f"<div style='font-size:13px;color:#0f172a;font-weight:700;"
        f"margin-top:3px;'>{name}</div>"
        f"<div style='font-size:11.5px;color:#475569;line-height:1.4;"
        f"margin-top:3px;'>{body}</div></div>"
    )

CCA_HTML = (
    "<div style='border:1px solid #e2e8f0;border-radius:10px;"
    "background:#f8fafc;padding:16px 18px;margin:8px 0;'>"
    "<div style='display:grid;grid-template-columns:"
    "repeat(5, minmax(0, 1fr));gap:8px;'>"
    + _cca_stage("#1d4ed8", "Stage 1 · LLM", "Route",
                 "Compile the question into a typed plan.")
    + _cca_stage("#16a34a", "Stage 2 · Code", "Execute",
                 "Run statistics deterministically on the STT.")
    + _cca_stage("#92400e", "Stage 3", "Seal",
                 "Lock the results with patient provenance. "
                 "Read-only downstream.", highlight=True)
    + _cca_stage("#1d4ed8", "Stage 4 · LLM", "Narrate",
                 "Write prose around the locked block. No "
                 "arithmetic, only quoting.")
    + _cca_stage("#16a34a", "Stage 5 · Code", "Verify",
                 "Check every number in the answer against the "
                 "sealed block.")
    + "</div></div>"
)
st.markdown(CCA_HTML, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────
# 6. Positioning vs prior work
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label' style='margin-top:24px;'>"
            "6. Why this could not be done before</p>",
            unsafe_allow_html=True)
st.markdown(
    "No prior approach handles all four needs together: free-text "
    "note input, archetype-stratified persistent structure, "
    "sparsity-aware inference, and cohort-level Q&A."
)

POSITIONING_HTML = (
    "<div style='overflow-x:auto;margin:8px 0 4px 0;'>"
    "<table style='width:100%;border-collapse:collapse;font-size:13px;"
    "border:1px solid #e2e8f0;'>"
    "<thead style='background:#f1f5f9;'>"
    "<tr>"
    "<th style='text-align:left;padding:7px 12px;font-weight:700;"
    "color:#0f172a;border:1px solid #e2e8f0;'>Approach</th>"
    "<th style='padding:7px 12px;font-weight:700;color:#475569;"
    "border:1px solid #e2e8f0;'>Note input</th>"
    "<th style='padding:7px 12px;font-weight:700;color:#475569;"
    "border:1px solid #e2e8f0;'>Stratified structure</th>"
    "<th style='padding:7px 12px;font-weight:700;color:#475569;"
    "border:1px solid #e2e8f0;'>Sparsity-aware</th>"
    "<th style='padding:7px 12px;font-weight:700;color:#475569;"
    "border:1px solid #e2e8f0;'>Cohort Q&amp;A</th>"
    "</tr></thead>"
    "<tbody>"
)
for row in [
    ("Clinical-NLP extraction", "partial", "—", "—", "—"),
    ("Medical LLMs",            "strong",  "—", "—", "weak*"),
    ("Text-to-SQL over EHR",    "—**",    "partial", "—", "partial"),
    ("Bayesian borrowing",      "—",       "—",  "strong", "—"),
    ("RAG",                     "strong",  "—",  "—", "weak***"),
]:
    POSITIONING_HTML += (
        "<tr>"
        f"<td style='padding:7px 12px;border:1px solid #e2e8f0;"
        f"color:#334155;'>{row[0]}</td>"
    )
    for cell in row[1:]:
        if cell == "strong":
            color = "#16a34a"
        elif cell == "partial":
            color = "#16a34a"
        elif cell.startswith("weak"):
            color = "#ca8a04"
        else:
            color = "#dc2626"
        POSITIONING_HTML += (
            f"<td style='text-align:center;padding:7px 12px;"
            f"border:1px solid #e2e8f0;color:{color};'>{cell}</td>"
        )
    POSITIONING_HTML += "</tr>"

# Our row
POSITIONING_HTML += (
    "<tr style='background:#eff6ff;'>"
    "<td style='padding:7px 12px;border:1px solid #e2e8f0;"
    "color:#0f172a;font-weight:700;'>Ask my data (this work)</td>"
    + "".join(
        "<td style='text-align:center;padding:7px 12px;"
        "border:1px solid #e2e8f0;color:#16a34a;font-weight:700;'>"
        "strong</td>" for _ in range(4)
    )
    + "</tr></tbody></table></div>"
    "<div style='font-size:11.5px;color:#64748b;margin-top:6px;"
    "line-height:1.5;'>"
    "* fabricates numbers, no patient-level provenance · "
    "** needs pre-structured EHR, not free-text notes · "
    "*** retrieves individuals, no aggregate computation."
    "</div>"
)
st.markdown(POSITIONING_HTML, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────
# Back to overview
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<div style='margin-top:24px;'></div>",
            unsafe_allow_html=True)
back_l2, _ = st.columns([1, 5])
with back_l2:
    if st.button("← Back to Overview ", key="back_bottom",
                 use_container_width=True):
        st.switch_page("app.py")

style.footer()
