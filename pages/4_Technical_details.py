"""Technical details — dark-themed companion to the Overview page."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import nav, style  # noqa: E402

st.set_page_config(page_title="Technical details — Ask my data", page_icon="🧠",
                                      layout="wide", initial_sidebar_state="collapsed")
style.inject()
nav.render("overview")

st.markdown(
        """
            <div class="hero">
                    <p class="hero-eyebrow">Technical details</p>
                            <h1 class="hero-title-inner">How Ask my data works, and why it could not be done before.</h1>
                                </div>
                                    """,
        unsafe_allow_html=True,
)

back_l, _ = st.columns([1, 5])
with back_l:
        if st.button("← Back to overview", use_container_width=True):
                    st.switch_page("app.py")

    # ── 1. The problem ─────────────────────────────────────────────────────────

st.markdown("<p class='section-label'>1. The problem</p>", unsafe_allow_html=True)

st.markdown(
        "<div class='info-line'>"
        "<b style='color:#f1f5f9;'>Sparsity across patients.</b> Stratifying a few-hundred-patient registry "
        "by grade × location × age × sex leaves many subgroups with a handful of cases each.<br/><br/>"
        "<b style='color:#f1f5f9;'>Noise inside each patient.</b> Years of free-text notes per person; "
        "the decisive information is buried in prose.<br/><br/>"
        "Existing tools address one or the other — none handles both while producing a queryable structure."
        "</div>",
        unsafe_allow_html=True,
)

# ── 2. Pipeline ────────────────────────────────────────────────────────────

st.markdown("<p class='section-label'>2. The framework, end to end</p>", unsafe_allow_html=True)

st.markdown(
        """
            <div style='display:grid;grid-template-columns:1fr 1.2fr 1fr;gap:1px;
                            background:#1e293b;border-radius:10px;overflow:hidden;margin:8px 0;'>
                                    <div style='background:#0a0a0a;padding:20px;'>
                                                <div style='font-size:10px;text-transform:uppercase;letter-spacing:0.1em;
                                                                        color:#334155;font-weight:600;margin-bottom:8px;'>Input</div>
                                                                                    <div style='font-size:14px;font-weight:600;color:#f1f5f9;margin-bottom:6px;'>
                                                                                                    Unstructured longitudinal notes</div>
                                                                                                                <div style='font-size:12.5px;color:#475569;'>Many notes per patient. Free text.</div>
                                                                                                                        </div>
                                                                                                                                <div style='background:#0d1526;padding:20px;border-left:2px solid #3b82f6;
                                                                                                                                                    border-right:2px solid #3b82f6;'>
                                                                                                                                                                <div style='font-size:10px;text-transform:uppercase;letter-spacing:0.1em;
                                                                                                                                                                                        color:#3b82f6;font-weight:600;margin-bottom:8px;'>Substrate</div>
                                                                                                                                                                                                    <div style='font-size:14px;font-weight:600;color:#f1f5f9;margin-bottom:6px;'>
                                                                                                                                                                                                                    Stratified Trajectory Tree (STT)</div>
                                                                                                                                                                                                                                <div style='font-size:12.5px;color:#475569;'>
                                                                                                                                                                                                                                                Records indexed by archetype, level, state, action — with
                                                                                                                                                                                                                                                                Contextual Power Priors borrowing across sparse cells.</div>
                                                                                                                                                                                                                                                                        </div>
                                                                                                                                                                                                                                                                                <div style='background:#0a0a0a;padding:20px;'>
                                                                                                                                                                                                                                                                                            <div style='font-size:10px;text-transform:uppercase;letter-spacing:0.1em;
                                                                                                                                                                                                                                                                                                                    color:#334155;font-weight:600;margin-bottom:8px;'>Outputs</div>
                                                                                                                                                                                                                                                                                                                                <div style='font-size:14px;font-weight:600;color:#f1f5f9;margin-bottom:6px;'>
                                                                                                                                                                                                                                                                                                                                                Four uses, one structure</div>
                                                                                                                                                                                                                                                                                                                                                            <div style='font-size:12.5px;color:#475569;'>
                                                                                                                                                                                                                                                                                                                                                                            Cohort Q&amp;A · per-patient evidence · action-conditioned outcomes · pathway summaries.
                                                                                                                                                                                                                                                                                                                                                                                        </div>
                                                                                                                                                                                                                                                                                                                                                                                                </div>
                                                                                                                                                                                                                                                                                                                                                                                                    </div>
                                                                                                                                                                                                                                                                                                                                                                                                        """,
        unsafe_allow_html=True,
)

# ── 3. STT ─────────────────────────────────────────────────────────────────

st.markdown("<p class='section-label'>3. Stratified Trajectory Tree</p>", unsafe_allow_html=True)

st.markdown(
        "<div style='font-size:13.5px;color:#64748b;margin-bottom:12px;line-height:1.6;'>"
        "Patients are grouped into <b style='color:#f1f5f9;'>cells</b> by their archetype "
        "(grade × location × age × sex). Each cell holds every patient with that exact profile, "
        "indexed by decision level (L1, L2, L3) and the action they took.</div>",
        unsafe_allow_html=True,
)

_BLUE = "#3b82f6"; _GREEN = "#16a34a"; _ORANGE = "#ea580c"

def _pt(label, color):
        return (f"<span style='display:inline-block;width:9px;height:9px;background:{color};"
                            f"border-radius:2px;margin-right:8px;vertical-align:middle;'></span>{label}")

STT_HTML = (
        "<div style='border:1px solid #1e293b;border-radius:10px;background:#0a0a0a;"
        "padding:18px 20px;'>"
        "<div style='display:grid;grid-template-columns:1.2fr 1.8fr;gap:24px;'>"
        "<div style='font-size:10px;text-transform:uppercase;letter-spacing:0.1em;"
        "font-weight:600;color:#334155;'>Patients</div>"
        "<div style='font-size:10px;text-transform:uppercase;letter-spacing:0.1em;"
        "font-weight:600;color:#334155;'>Stratified into cells by archetype</div>"
        "</div>"
        "<div style='display:grid;grid-template-columns:1.2fr 1.8fr;gap:24px;margin-top:10px;'>"
        f"<div style='font-size:12.5px;color:#64748b;line-height:2.2;'>"
        f"{_pt('Patient A · grade 1 · skull base · 55F', _BLUE)}<br/>"
        f"{_pt('Patient B · grade 1 · convexity · 42M', _GREEN)}<br/>"
        f"{_pt('Patient C · grade 2 · parasagittal · 67F', _ORANGE)}<br/>"
        f"{_pt('Patient D · grade 1 · skull base · 60F', _BLUE)}"
        f"</div>"
        "<div>"
        f"<div style='border:1px solid {_BLUE}44;border-left:3px solid {_BLUE};"
        f"border-radius:0 6px 6px 0;background:#050505;padding:10px 12px;margin-bottom:8px;'>"
        f"<div style='font-size:12px;font-weight:600;color:#f1f5f9;'>{_pt('grade 1 · skull base · 50–65 · F', _BLUE)}</div>"
        f"<div style='font-size:11.5px;color:#475569;margin-top:4px;'>"
        f"Patients A, D &nbsp;·&nbsp; "
        f"<span style='background:#052e16;color:#4ade80;padding:1px 8px;border-radius:4px;'>L1: Watch &amp; Wait</span> "
        f"<span style='background:#052e16;color:#4ade80;padding:1px 8px;border-radius:4px;'>L2: Watch &amp; Wait</span></div></div>"
        f"<div style='border:1px solid {_GREEN}44;border-left:3px solid {_GREEN};"
        f"border-radius:0 6px 6px 0;background:#050505;padding:10px 12px;margin-bottom:8px;'>"
        f"<div style='font-size:12px;font-weight:600;color:#f1f5f9;'>{_pt('grade 1 · convexity · &lt;50 · M', _GREEN)}</div>"
        f"<div style='font-size:11.5px;color:#475569;margin-top:4px;'>"
        f"Patient B &nbsp;·&nbsp; "
        f"<span style='background:#0d1526;color:#93c5fd;padding:1px 8px;border-radius:4px;'>L1: Surgery</span></div></div>"
        f"<div style='border:1px solid {_ORANGE}44;border-left:3px solid {_ORANGE};"
        f"border-radius:0 6px 6px 0;background:#050505;padding:10px 12px;'>"
        f"<div style='font-size:12px;font-weight:600;color:#f1f5f9;'>{_pt('grade 2 · parasagittal · &gt;65 · F', _ORANGE)}</div>"
        f"<div style='font-size:11.5px;color:#475569;margin-top:4px;'>"
        f"Patient C &nbsp;·&nbsp; "
        f"<span style='background:#0d1526;color:#93c5fd;padding:1px 8px;border-radius:4px;'>L1: Surgery</span> "
        f"<span style='background:#1f0a0a;color:#fca5a5;padding:1px 8px;border-radius:4px;'>L2: Radiation</span></div></div>"
        "</div></div></div>"
)

st.markdown(STT_HTML, unsafe_allow_html=True)

# ── 4. CPP ─────────────────────────────────────────────────────────────────

st.markdown("<p class='section-label'>4. Contextual Power Priors — sparsity fix</p>", unsafe_allow_html=True)

st.markdown(
        "<div style='font-size:13.5px;color:#64748b;margin-bottom:12px;line-height:1.6;'>"
        "Most cells are sparse. CPP borrows evidence from neighbouring cells, weighted by how "
        "similar each neighbour's archetype is to the target cell.</div>",
        unsafe_allow_html=True,
)

def _cpp_row(diff, archetype, n, weight):
        bar_color = "#4ade80" if weight>=0.65 else ("#facc15" if weight>=0.40 else "#f87171")
        pct = int(weight*100)
        return (
            "<div style='display:grid;grid-template-columns:1.1fr 1.6fr 0.5fr 1.4fr;gap:14px;"
            "align-items:center;padding:10px 12px;border:1px solid #1e293b;border-radius:6px;"
            "background:#0a0a0a;margin-bottom:6px;'>"
            f"<div style='font-size:12px;color:#475569;'><i style='font-size:11px;'>differs by</i><br/>"
            f"<b style='color:#f1f5f9;'>{diff}</b></div>"
            f"<div style='font-size:12px;color:#64748b;'>{archetype}</div>"
            f"<div style='font-size:12px;color:#475569;text-align:right;'>n = {n}</div>"
            "<div>"
            "<div style='height:6px;background:#1e293b;border-radius:3px;overflow:hidden;'>"
            f"<div style='width:{pct}%;height:100%;background:{bar_color};'></div></div>"
            f"<div style='font-size:11px;color:{bar_color};font-weight:600;margin-top:3px;'>"
            f"weight {weight:.2f}</div></div></div>"
        )

CPP_HTML = (
        "<div style='border:1px solid #1e293b;border-radius:10px;background:#0a0a0a;padding:18px 20px;'>"
        "<div style='border:1px solid #1e3a5f;border-radius:8px;padding:14px;background:#0d1526;margin-bottom:14px;'>"
        "<div style='font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:#3b82f6;"
        "font-weight:600;margin-bottom:6px;'>Target cell — sparse</div>"
        "<div style='font-size:14px;font-weight:600;color:#f1f5f9;'>grade 2 · parasagittal · &gt;65 · F</div>"
        "<div style='font-size:12px;color:#475569;margin-top:4px;'>Only <b style='color:#f87171;'>n = 3</b> patients.</div></div>"
        "<div style='font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:#334155;"
        "font-weight:600;margin-bottom:8px;'>Neighbours contribute, weighted by similarity</div>"
        + _cpp_row("age band",  "grade 2 · parasagittal · 50–65 · F", 7, 0.78)
        + _cpp_row("sex",       "grade 2 · parasagittal · &gt;65 · M", 4, 0.55)
        + _cpp_row("location",  "grade 2 · convexity · &gt;65 · F",    5, 0.42)
        + _cpp_row("grade",     "grade 1 · parasagittal · &gt;65 · F", 12, 0.18)
        + "</div>"
)

st.markdown(CPP_HTML, unsafe_allow_html=True)

# ── 5. Compute/narrate separation ──────────────────────────────────────────

st.markdown("<p class='section-label'>5. Q&amp;A: separating compute from narrate</p>", unsafe_allow_html=True)

st.markdown(
        "<div class='info-line'>"
        "A language model given the cohort directly tends to <b style='color:#f87171;'>invent aggregate numbers</b>, "
        "<b style='color:#f87171;'>conflate facts across patients</b>, and <b style='color:#f87171;'>lose time anchors</b>. "
        "Our fix: statistics are computed in code, sealed, then narrated. Every number is verified against the sealed block."
        "</div>",
        unsafe_allow_html=True,
)

def _stage(badge_color, badge, name, body, highlight=False):
        bg = "#0d1a2e" if highlight else "#0a0a0a"
        border = f"1px solid #d97706" if highlight else "1px solid #1e293b"
        return (
            f"<div style='border:{border};border-radius:8px;padding:12px 14px;background:{bg};'>"
            f"<div style='font-size:10px;font-weight:700;color:{badge_color};"
            f"text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px;'>{badge}</div>"
            f"<div style='font-size:13px;color:#f1f5f9;font-weight:600;margin-bottom:4px;'>{name}</div>"
            f"<div style='font-size:11.5px;color:#475569;line-height:1.45;'>{body}</div></div>"
        )

CCA_HTML = (
        "<div style='border:1px solid #1e293b;border-radius:10px;background:#0a0a0a;padding:16px;margin:8px 0;'>"
        "<div style='display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;'>"
        + _stage("#3b82f6","Stage 1 · LLM","Route","Map the question to a typed analysis plan.")
        + _stage("#4ade80","Stage 2 · Code","Execute","Run statistics deterministically on the STT.")
        + _stage("#d97706","Stage 3","Seal","Lock the results with patient provenance. Read-only downstream.", highlight=True)
        + _stage("#3b82f6","Stage 4 · LLM","Narrate","Write prose around the sealed block — no arithmetic, only quoting.")
        + _stage("#4ade80","Stage 5 · Code","Verify","Check every number in the prose against the sealed block.")
        + "</div></div>"
)

st.markdown(CCA_HTML, unsafe_allow_html=True)

# ── 6. Prior work ──────────────────────────────────────────────────────────

st.markdown("<p class='section-label'>6. Why this could not be done before</p>", unsafe_allow_html=True)

ROWS = [
        ("Clinical-NLP extraction", "partial","—","—","—"),
        ("Medical LLMs",            "strong", "—","—","weak*"),
        ("Text-to-SQL over EHR",    "—**",   "partial","—","partial"),
        ("Bayesian borrowing",      "—",      "—","strong","—"),
        ("RAG",                     "strong", "—","—","weak***"),
]

COLOR = {"strong":"#4ade80","partial":"#facc15","—":"#f87171","weak*":"#facc15","weak***":"#facc15","—**":"#f87171"}

TABLE = (
        "<div style='overflow-x:auto;margin:8px 0;'>"
        "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
        "<thead><tr style='border-bottom:1px solid #1e293b;'>"
        "<th style='text-align:left;padding:8px 12px;color:#334155;font-weight:600;'>Approach</th>"
        + "".join(f"<th style='padding:8px 12px;color:#334155;font-weight:600;text-align:center;'>{h}</th>"
                                for h in ["Note input","Stratified structure","Sparsity-aware","Cohort Q&A"])
        + "</tr></thead><tbody>"
)

for row in ROWS:
        TABLE += "<tr style='border-bottom:1px solid #1e293b;'>"
        TABLE += f"<td style='padding:8px 12px;color:#64748b;'>{row[0]}</td>"
        for cell in row[1:]:
                    c = COLOR.get(cell, "#64748b")
                    TABLE += f"<td style='text-align:center;padding:8px 12px;color:{c};font-weight:500;'>{cell}</td>"
                TABLE += "</tr>"

TABLE += (
        "<tr style='background:#0d1526;border-bottom:1px solid #1e293b;'>"
        "<td style='padding:8px 12px;color:#f1f5f9;font-weight:700;'>Ask my data (this work)</td>"
        + "".join(f"<td style='text-align:center;padding:8px 12px;color:#4ade80;font-weight:700;'>strong</td>" for _ in range(4))
        + "</tr></tbody></table></div>"
        + "<div style='font-size:11.5px;color:#334155;margin-top:6px;line-height:1.5;'>"
        + "* fabricates numbers, no provenance &nbsp;·&nbsp;  needs pre-structured EHR &nbsp;·&nbsp; * retrieves individuals, no aggregate computation"
        + "</div>"
)

st.markdown(TABLE, unsafe_allow_html=True)

st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)

back_l2, _ = st.columns([1, 5])
with back_l2:
        if st.button("← Back to overview ", key="back_bottom", use_container_width=True):
                    st.switch_page("app.py")

style.footer()
