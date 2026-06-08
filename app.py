"""
cdt_webapp_v4 — interactive clinician-facing instantiation of the
cohort-to-text framework for meningioma decision support.

Overview / landing page. Run with:
    streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import nav, style                       # noqa: E402

st.set_page_config(
    page_title="Ask my data — meningioma cohort",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)
style.inject()
nav.render("overview")

# Cohort is intentionally NOT loaded on the overview — the substantive
# cohort tooling lives on the Cohort page. Keeping the overview light
# loads it faster on first paint.

# ── Hero ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero">
      <p class="hero-eyebrow">Ask my data &middot; meningioma cohort</p>
      <h1 class="hero-title">Population-level clinical questions answered
      with exact counts, confidence intervals, and patient-level provenance
      &mdash; from longitudinal notes.</h1>
      <p class="hero-sub">
        Ask my data turns unstructured longitudinal meningioma notes into a
        structured, queryable substrate. A typed compiler maps each free-form
        question to deterministic code; all statistics are computed by code
        and sealed in a locked stats block before a language model narrates
        the result. Numerical fabrication is prevented by architecture, not
        by the model.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# (Demo-data banner and LOADED COHORT stat panel intentionally omitted on
# the overview — cohort details live on the Cohort page where they are
# directly actionable.)

# ── How the framework works ────────────────────────────────────────────────
st.markdown("<p class='section-label'>How the framework works</p>",
            unsafe_allow_html=True)
steps = [
    ("Extract",
     "A multi-pass language-model pipeline reads each patient's longitudinal "
     "notes and emits a structured record over a fixed schema: demographics, "
     "diagnosis, and a sequence of dated events with tumour measurement, "
     "intervention, performance status, recurrence, and molecular-testing "
     "fields. Provenance flags for copy-forwarded text, uncertain facts, "
     "inferred measurements, and date inconsistencies are surfaced, not "
     "hidden."),
    ("Stratify with similarity-weighted borrowing",
     "Records are indexed by the patient's archetype (grade, location, age "
     "band, sex), decision level, history-conditioned clinical state "
     "(tumour-size band, symptoms), and action (surveillance, surgery, "
     "radiation). Treatment history is embedded in the state key so "
     "trajectories never collide. When a stratum is sparse, the Contextual "
     "Power Prior borrows similarity-weighted evidence from neighbouring "
     "archetypes; the effective sample size is reported alongside every "
     "recommendation, so evidential sparsity is never silently smoothed "
     "into apparent certainty."),
    ("Recommend &amp; answer",
     "<b>For a single patient:</b> at each decision level, the archetype-"
     "similar historical patients are surfaced with their outcomes and "
     "similarity weights; the action-conditioned posterior, the most common "
     "observed action in that archetype, and the clinician's actual choice "
     "are shown side by side. A counterfactual analysis reports the change "
     "in estimated functional probability between candidate actions, with "
     "its effective sample size, so a recommendation can be audited against "
     "the observed outcome.<br/><br/>"
     "<b>For a population question:</b> the free-form question compiles "
     "into a typed program over the registry schema (filter, aggregate, "
     "compare, stratify, trajectory). The compiled program runs in "
     "deterministic code &mdash; Clopper-Pearson intervals, Fisher's exact, "
     "Cochran-Mantel-Haenszel pooling, multi-covariate inverse-probability "
     "weighting, E-values, minimum detectable effects &mdash; and seals "
     "every statistic with a causal-tier label and patient-level provenance "
     "into a locked stats block. The language model is invoked only to "
     "write prose around the locked block. A post-generation verifier "
     "checks that every numeric token in the answer traces back to the "
     "block; nothing is invented."),
]
for i, (title, desc) in enumerate(steps, 1):
    st.markdown(
        f"""
        <div class="step">
          <div class="step-num">{i}</div>
          <div class="step-body">
            <p class="step-title">{title}</p>
            <p class="step-desc">{desc}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── What you can do here ───────────────────────────────────────────────────
st.markdown("<p class='section-label'>What you can do in this demo</p>",
            unsafe_allow_html=True)
st.markdown(
    """
    - **Try it.** Pick a synthetic patient and walk through each decision
      level: the outcome-optimal action under the posterior, the most common
      action among archetype-similar patients, and the clinician's observed
      choice, all side by side.
    - **Recommendation.** Full audit trail for a single decision: archetype,
      history-conditioned state, the archetype-similar historical patients
      with their outcomes and similarity weights, the action-conditioned
      posterior with effective sample size, and a counterfactual analysis
      reporting the change in estimated functional probability between
      candidate actions.
    - **Cohort & grounded Q&amp;A.** Live descriptive statistics for any
      demographic or tumour-profile filter, treatment-pathway diagrams whose
      branch widths encode patient counts, an extraction data-quality panel,
      and a free-form question box wired to the cohort-to-text pipeline. The
      router classifies each typed question into one of nine analysis types;
      the executor runs Fisher / Cochran-Mantel-Haenszel / IPW / E-value as
      appropriate; the synthesiser writes prose with every number provably
      computed.
    """
)

# ── Known limits ───────────────────────────────────────────────────────────
st.markdown("<p class='section-label'>Known limits</p>",
            unsafe_allow_html=True)
st.markdown(
    """
    - **Semantic predicate limit.** The firewall guarantees faithful
      narration of whatever was computed, but it cannot guarantee that the
      compiled program is the right interpretation of the question. A
      verified answer can still be vacuous if the compiler maps to the wrong
      predicate. The structural-uncertainty signal is the per-question
      detector for this failure; it does not eliminate it.
    - **Observational.** Action-conditioned outcomes are decision-support
      signals, not causal effects. Real-data estimates are subject to
      confounding by indication.
    - **Three actions.** Surveillance, surgery, radiation. Sub-modalities
      (GTR vs STR, SRS vs FSRT, proton vs photon) are not modelled in this
      demo.
    - **Coarse state.** Tumour size and symptoms are discretised; very long
      trajectories are truncated at the third decision level.
    - **Performance-only outcome.** The demo binarises functional status
      from the last recorded performance score (ECOG / KPS). Survival
      endpoints are out of scope.
    - **Not for clinical use.** This is decision support and illustrative
      output, not autonomous decision-making.
    """
)

st.info("Open **Try it** to pick a synthetic patient, **Recommendation** for "
        "a full audit trail at a single decision, or **Cohort** for free-form "
        "grounded question answering.")

style.footer()
