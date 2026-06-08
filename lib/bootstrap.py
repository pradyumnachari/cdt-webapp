"""Session-cached cohort loading, shared by every page."""

from __future__ import annotations

import streamlit as st

from .config import COHORT_CSV
from .data_loader import load_cohort


@st.cache_resource(show_spinner="Loading patient cohort…")
def get_cohort() -> dict:
    """Load and normalize the cohort once per session."""
    if not COHORT_CSV.exists():
        raise FileNotFoundError(
            f"Cohort CSV not found: {COHORT_CSV}\n"
            "Set lib/config.py:COHORT_CSV or the CDT_COHORT_CSV env var."
        )
    return load_cohort(COHORT_CSV)
