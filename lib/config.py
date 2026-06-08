"""
Configuration for cdt_webapp_v3.

================================================================
  >>> WHERE TO PROVIDE YOUR REAL DATA FILE <<<
================================================================
This app reads ONE CSV file. That CSV must have a column named
`generation` (the "third column") holding, per row, a JSON string
in the v7 patient-extraction schema:

    { "patient_demographics": {...}, "events": [ {...}, ... ] }

and an identifier column named `patient_id` (or `MRN`).

To use your real data, do EITHER of the following:

  1. Drop your file in   cdt_webapp_v3/data/   and set
     COHORT_CSV below to its filename, e.g.:
         COHORT_CSV = DATA_DIR / "my_real_cohort.csv"

  2. Or set the environment variable CDT_COHORT_CSV to an
     absolute path before launching streamlit:
         export CDT_COHORT_CSV=/abs/path/to/cohort.csv

The bundled `dummy_cohort.csv` is a synthetic stand-in produced by
`tools/build_dummy_csv.py`. It has the exact same format as real
data, so nothing else needs to change when you swap files.
================================================================
"""

from __future__ import annotations

import os
from pathlib import Path

WEBAPP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = WEBAPP_DIR / "data"

# Default demo file. Replace with your real cohort CSV (see header above).
COHORT_CSV = DATA_DIR / "dummy_cohort.csv"

# Environment override wins if set.
if os.environ.get("CDT_COHORT_CSV"):
    COHORT_CSV = Path(os.environ["CDT_COHORT_CSV"])

# Column names expected in the CSV.
GENERATION_COLUMN = "generation"
ID_COLUMNS = ("patient_id", "MRN")  # first one found is used

# CDT parameters.
K_MAX_LEVELS = 3       # decision levels surfaced per patient
TOP_K_SIMILAR = 8      # similar patients shown as evidence
TEST_FRACTION = 0.2    # held-out fraction (deterministic split)
RANDOM_SEED = 42

IS_DEMO_DATA = COHORT_CSV.name == "dummy_cohort.csv"
