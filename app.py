"""
cdt_webapp_v4 — Ask my data (meningioma cohort, retrospective explorer).

Overview / landing page. Plain-language, clinician-focused, concise.
Technical detail lives on pages/4_Technical_details.py and is reached
only via the link at the bottom of this page.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import nav, style  # noqa: E402

st.set_page_config(
    page_title="Ask my data — meningioma cohort",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="hidden",
)
style.inject()
nav.render("overview")


# ─────────────────────────────────────────────────────────────────────────
# Hero
# ─────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero">
      <p class="hero-eyebrow">Ask my data &middot; meningioma cohort</p>
      <h1 class="hero-title">
        A retrospective explorer for longitudinal meningioma care.</h1>
      <p class="hero-sub">
        Meningioma is managed over years, not in a single episode. The
        decisions live in free-text notes. Ask my data turns those notes
        into a structured view of the cohort you can explore directly.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────
# What you can do here — three compact cards
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label'>What you can do here</p>",
            unsafe_allow_html=True)
st.markdown(
    """
    <div style='display:grid;grid-template-columns:1fr 1fr 1fr;
                gap:14px;margin-top:6px;'>
      <div style='border:1px solid #e2e8f0;border-radius:10px;
                  padding:14px 16px;background:#fff;'>
        <div style='font-size:11.5px;text-transform:uppercase;
                    letter-spacing:0.10em;font-weight:700;color:#1d4ed8;'>
          Ask my data
        </div>
        <div style='font-size:15px;font-weight:700;color:#0f172a;
                    margin:4px 0 4px 0;'>Type a question</div>
        <div style='font-size:13px;color:#334155;line-height:1.55;'>
          Free-form clinical questions, answered with statistics
          computed in code — not invented.
        </div>
      </div>
      <div style='border:1px solid #e2e8f0;border-radius:10px;
                  padding:14px 16px;background:#fff;'>
        <div style='font-size:11.5px;text-transform:uppercase;
                    letter-spacing:0.10em;font-weight:700;color:#1d4ed8;'>
          Visualizations
        </div>
        <div style='font-size:15px;font-weight:700;color:#0f172a;
                    margin:4px 0 4px 0;'>Explore the cohort</div>
        <div style='font-size:13px;color:#334155;line-height:1.55;'>
          Filter by grade, location, age, sex. See outcomes and
          treatment pathways live.
        </div>
      </div>
      <div style='border:1px solid #e2e8f0;border-radius:10px;
                  padding:14px 16px;background:#fff;'>
        <div style='font-size:11.5px;text-transform:uppercase;
                    letter-spacing:0.10em;font-weight:700;color:#1d4ed8;'>
          Similar patients
        </div>
        <div style='font-size:15px;font-weight:700;color:#0f172a;
                    margin:4px 0 4px 0;'>Look up one case</div>
        <div style='font-size:13px;color:#334155;line-height:1.55;'>
          For one patient at one decision point, see how
          similar historical patients did.
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────
# Inputs and outputs — single compact strip
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label' style='margin-top:24px;'>"
            "Inputs and outputs</p>",
            unsafe_allow_html=True)
st.markdown(
    """
    <div style='display:grid;grid-template-columns:1fr 0.08fr 1fr;
                gap:14px;align-items:center;margin-top:4px;'>
      <div style='border:1px solid #e2e8f0;border-radius:10px;
                  padding:14px 16px;background:#f8fafc;'>
        <div style='font-size:11.5px;text-transform:uppercase;
                    letter-spacing:0.10em;font-weight:700;
                    color:#475569;'>Input</div>
        <div style='font-size:15px;font-weight:700;color:#0f172a;
                    margin:4px 0 6px 0;'>
          Longitudinal free-text notes
        </div>
        <div style='font-size:13px;color:#334155;line-height:1.55;'>
          Imaging, op notes, clinic visits, radiation summaries,
          pathology — as they appear in the chart.
        </div>
      </div>
      <div style='text-align:center;color:#94a3b8;font-size:24px;'>→</div>
      <div style='border:1px solid #e2e8f0;border-radius:10px;
                  padding:14px 16px;background:#eff6ff;'>
        <div style='font-size:11.5px;text-transform:uppercase;
                    letter-spacing:0.10em;font-weight:700;
                    color:#1d4ed8;'>Output</div>
        <div style='font-size:15px;font-weight:700;color:#0f172a;
                    margin:4px 0 6px 0;'>
          Cohort &amp; patient-level evidence
        </div>
        <div style='font-size:13px;color:#334155;line-height:1.55;'>
          Plain-English answers · cohort summaries · treatment-pathway
          diagrams · per-patient evidence panels.
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────
# Key terms — compact one-line definitions
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label' style='margin-top:24px;'>"
            "Key terms</p>",
            unsafe_allow_html=True)
st.markdown(
    """
    <div style='border:1px solid #e2e8f0;border-radius:10px;
                background:#f8fafc;padding:14px 18px;
                font-size:13.5px;color:#334155;line-height:1.85;'>
      <b>Decision levels — L1 / L2 / L3.</b>
      Sequential decision points: L1 first, L2 next (recurrence, growth,
      new symptoms), L3 if reached. Many patients never reach L3.
      <br/>
      <b>Action.</b>
      <span style='background:#bbf7d0;padding:1px 7px;border-radius:4px;
                   font-weight:600;color:#0f172a;'>Watch &amp; Wait</span>,
      <span style='background:#ddd6fe;padding:1px 7px;border-radius:4px;
                   font-weight:600;color:#0f172a;'>Surgery</span>, or
      <span style='background:#fecaca;padding:1px 7px;border-radius:4px;
                   font-weight:600;color:#0f172a;'>Radiation</span>.
      <br/>
      <b>Archetype.</b>
      WHO grade × location × age band × sex.
      <br/>
      <b>Functional rate.</b>
      Fraction with ECOG&nbsp;0–2 or KPS&nbsp;≥&nbsp;70 at last
      follow-up.
      <br/>
      <b>Similar patients.</b>
      Top historical patients whose archetype most closely matches.
    </div>
    """,
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────
# Why this is new + validation in one block
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label' style='margin-top:24px;'>"
            "Why this is new</p>",
            unsafe_allow_html=True)
st.markdown(
    """
    Subgroup statistics from a hospital's longitudinal patient
    progress notes are hard: decisions live in free text, subgroups
    are small, and a language model that just reads the notes tends to
    invent numbers. The framework structures the notes, borrows
    evidence across similar subgroups when one is sparse, and computes
    every statistic in code *before* a language model writes any
    prose. A separate check then confirms every number in the prose
    traces back to that sealed block.
    """
)


# ─────────────────────────────────────────────────────────────────────────
# Caveat + tech link
# ─────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="warn-line" style="margin-top:20px;font-size:13.5px;">
      <b>Not for clinical use.</b> Research demo over synthetic data.
      Outputs are illustrative.
    </div>
    """,
    unsafe_allow_html=True,
)

btn_col, _ = st.columns([2, 5])
with btn_col:
    if st.button("See the technical details →",
                 use_container_width=True, type="primary"):
        st.switch_page("pages/4_Technical_details.py")

style.footer()
