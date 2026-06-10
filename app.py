"""
cdt_webapp_v4 — Ask my data (meningioma cohort, retrospective explorer).

Overview / landing page. Run with:
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
    initial_sidebar_state="collapsed",
)
style.inject()
nav.render("overview")

# Cohort is intentionally NOT loaded on the overview — the substantive
# tooling lives on the Visualizations and Similar-patients tabs. Keeping
# the overview light loads it faster on first paint.

# ── Hero ──────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero">
      <p class="hero-eyebrow">Ask my data &middot; meningioma cohort</p>
      <h1 class="hero-title">A retrospective explorer over a synthetic
      meningioma cohort.</h1>
      <p class="hero-sub">
        Ask my data is a clinician-facing demo for exploring how patients
        in a longitudinal meningioma registry were treated and how they did.
        Browse cohort-level statistics, ask plain-English questions and get
        answers grounded in the underlying data, or inspect any single
        patient alongside archetype-similar historical patients to see
        what they received and how they did. The system describes what is
        in the data; it does not recommend treatment.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── What you can do here (plain language, descriptive verbs) ──────────────
st.markdown("<p class='section-label'>What you can do here</p>",
            unsafe_allow_html=True)
st.markdown(
    """
    - **Ask my data.** Type a clinical question in plain English. The
      system maps it to a deterministic analysis, runs the statistics in
      code, and writes a short answer. Every number in the answer was
      computed by code, not by the model.
    - **Visualizations.** Filter the cohort by demographics or tumour
      profile and see functional-outcome rates, treatment-pathway flow
      diagrams, and the extraction provenance flags.
    - **Similar patients & evidence.** Pick a patient and a decision
      point. See what archetype-similar historical patients received at
      the same point and how they did, alongside the patient's own
      observed pathway.
    """
)

# ── Important caveats (kept above the fold) ───────────────────────────────
st.markdown(
    """
    <div class="warn-line" style="font-size:13.5px;">
      <b>Not for clinical use.</b> This is a research demo over synthetic
      data. The outputs are illustrative and must not be used to inform
      patient care.
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Technical detail (collapsed by default, methodology lives here) ───────
with st.expander("How it works (technical detail)", expanded=False):
    st.markdown(
        """
        The system has three coupled components.

        **Extraction.** A multi-pass language-model pipeline reads each
        patient's longitudinal notes and emits a structured record over a
        fixed schema: demographics, diagnosis, and a sequence of dated
        events with tumour measurement, intervention, performance status,
        recurrence, and molecular-testing fields. Provenance flags for
        copy-forwarded text, uncertain facts, inferred measurements, and
        date inconsistencies are surfaced rather than hidden.

        **Stratified Trajectory Tree + Contextual Power Prior.** Records
        are indexed by the patient's archetype (grade, location, age band,
        sex), decision level, history-conditioned clinical state, and
        action. Treatment history is embedded in the state key so
        trajectories never collide. When a stratum is sparse, similarity-
        weighted evidence is borrowed from neighbouring archetypes; the
        effective sample size is reported alongside every estimate so
        evidential sparsity is never silently smoothed into apparent
        certainty.

        **Cohort-to-text question answering.** Free-form questions compile
        into a typed program over the registry schema (filter, aggregate,
        compare, stratify, trajectory, funnel, anchor). The compiled
        program runs in deterministic code — Clopper-Pearson intervals,
        Fisher's exact test, Cochran-Mantel-Haenszel pooling, multi-
        covariate inverse-probability weighting, E-values, minimum
        detectable effects — and seals every statistic with a causal-tier
        label and patient-level provenance into a locked stats block.

        **Compute / narrate firewall.** The language model is invoked only
        to write prose around the locked block; it cannot perform
        arithmetic. A post-generation verifier checks that every numeric
        token in the answer traces back to the block. Numerical grounding
        is a property of the architecture, not of the model.

        **Causal language is constrained.** Every statistic carries a
        causal tier (association, adjusted association, sensitivity,
        finding) with a corresponding language contract. Causal verbs are
        downgraded when the underlying tier does not support them.
        """
    )

    st.markdown("<p class='section-label' style='margin-top:18px;'>"
                "Known limits</p>", unsafe_allow_html=True)
    st.markdown(
        """
        - **Synthetic data.** The demo cohort is generated from a
          structural causal model so the population-level ground truth is
          known by construction. It is not a real registry.
        - **Semantic predicate limit.** The firewall guarantees faithful
          narration of whatever was computed, but cannot guarantee the
          compiled program is the right interpretation of the question.
          A verified answer can still be vacuous if the compiler maps to
          the wrong predicate.
        - **Observational.** Action-conditioned outcomes are descriptive
          signals, not causal effects. They are subject to confounding by
          indication.
        - **Three actions.** Surveillance, surgery, radiation. Sub-
          modalities (GTR vs STR, SRS vs FSRT, proton vs photon) are not
          modelled.
        - **Coarse state.** Tumour size and symptoms are discretised; very
          long trajectories are truncated at the third decision level.
        - **Performance-only outcome.** The demo binarises functional
          status from the last recorded performance score (ECOG / KPS).
          Survival endpoints are out of scope.
        """
    )

st.info("Open **Ask my data** to ask a free-form clinical question, "
        "**Visualizations** to explore the cohort by filter, or "
        "**Similar patients & evidence** to inspect one patient alongside "
        "their archetype-similar historical peers.")

style.footer()
