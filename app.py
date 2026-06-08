"""
cdt_webapp_v3 — Clinical Decision Tree GUI for real extraction data.

Overview / landing page. Run with:
    streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import nav, style                       # noqa: E402
from lib.bootstrap import get_cohort              # noqa: E402
from lib.config import COHORT_CSV, IS_DEMO_DATA   # noqa: E402

st.set_page_config(
    page_title="CDT — real-data recommender",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)
style.inject()
nav.render("overview")

# ── Load cohort (guarded) ──────────────────────────────────────────────────
try:
    cohort = get_cohort()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load cohort:\n\n{exc}")
    st.stop()

patients = cohort["patients"]
n_train, n_test = len(cohort["train"]), len(cohort["test"])

# ── Hero ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero">
      <p class="hero-eyebrow">Clinical Decision Tree · meningioma</p>
      <h1 class="hero-title">Evidence-grounded treatment recommendations
      from real extracted patient pathways.</h1>
      <p class="hero-sub">
        This app reads longitudinal meningioma pathways extracted from
        clinical notes and, at each decision point, recommends watch &amp;
        wait, surgery, or radiation — grounded in archetype-similar
        historical patients, not a black-box prior.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Demo-data banner ───────────────────────────────────────────────────────
if IS_DEMO_DATA:
    st.markdown(
        f"""
        <div class="warn-line">
          <b>Running on demo data.</b> The loaded cohort is a synthetic
          stand-in (<code>{COHORT_CSV.name}</code>) with the exact same
          format as real extraction output. To use real data, set
          <code>COHORT_CSV</code> in <code>lib/config.py</code> or the
          <code>CDT_COHORT_CSV</code> environment variable — no other
          change is needed.
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Cohort snapshot ────────────────────────────────────────────────────────
st.markdown("<p class='section-label'>Loaded cohort</p>",
            unsafe_allow_html=True)
if cohort["errors"]:
    st.caption(f"{len(cohort['errors'])} row(s) could not be parsed and "
               f"were skipped.")

c1, c2, c3, c4 = st.columns(4)
for col, label, value in [
    (c1, "Patients", len(patients)),
    (c2, "Training pathways", n_train),
    (c3, "Held-out patients", n_test),
    (c4, "Decision levels / patient", "up to 3"),
]:
    with col:
        st.markdown(
            f"<div class='stat-card'><p class='stat-card-label'>{label}</p>"
            f"<p class='stat-card-value'>{value}</p></div>",
            unsafe_allow_html=True,
        )

# ── How it works ───────────────────────────────────────────────────────────
st.markdown("<p class='section-label'>How it works</p>",
            unsafe_allow_html=True)
steps = [
    ("Extract", "Each patient is one JSON in the CSV's <code>generation</code> "
                "column — demographics plus a list of clinical events."),
    ("Stratify", "Age, gender, grade and location define the patient's "
                 "archetype; tumour size and symptoms define the per-event "
                 "state."),
    ("Derive pathway", "Consecutive same-action events are collapsed into "
                       "decision levels — the observed treatment trajectory."),
    ("Recommend", "At each level, P(functional | action) is estimated from "
                  "similarity-weighted historical outcomes; the argmax action "
                  "is recommended and the observed action is scored against "
                  "it."),
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

# ── Limitations ────────────────────────────────────────────────────────────
st.markdown("<p class='section-label'>Limitations</p>",
            unsafe_allow_html=True)
st.markdown(
    """
    - **Observational.** Estimates are associational — similar patients who
      took an action, not a randomised comparison.
    - **Performance-only.** The real-data pipeline models functional outcome
      (ECOG / KPS); it does not predict survival.
    - **Three actions.** Watch &amp; wait, surgery, radiation. Sub-action
      distinctions (GTR vs STR, SRS vs FSRT) are not modelled.
    - **Extraction noise.** Events carry provenance flags (copy-paste,
      uncertain, inferred size, date inconsistency) — surfaced in the
      Cohort tab so the data quality is visible, not hidden.
    - **Not for clinical use.** Recommendations are illustrative.
    """
)

st.info("Open **Try it** to pick a patient, or **Recommendation** to inspect "
        "a single decision in detail.")

style.footer()
