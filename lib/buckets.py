"""
Bucketing + action constants for cdt_webapp_v4.

Self-contained: the v7 pipeline's bucket logic is inlined here so the app
has zero imports from the heavy pipeline packages. Size thresholds match
v2/v3/v4/v7:  <2cm = small, 2-4cm = medium, >=4cm = large.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

# ── Action space (real-data CDT: 3 actions, performance-only) ──────────────
ACTIONS = ["wait_and_watch", "surgery", "radiation"]

ACTION_LABELS = {
    "wait_and_watch": "Watch & Wait",
    "surgery": "Surgery",
    "radiation": "Radiation",
}

ACTION_COLORS = {
    "wait_and_watch": "#16a34a",
    "surgery": "#2563eb",
    "radiation": "#dc2626",
}

OUTCOME_COLORS = {
    "functional": "#16a34a",
    "impaired": "#ea580c",
    "unknown": "#94a3b8",
}

# ── Archetype encoding ─────────────────────────────────────────────────────
AGE_MAP = {"<50": 0, "50-65": 1, ">=65": 2}
GENDER_MAP = {"M": 0, "F": 1}
GRADE_MAP = {"grade_1": 0, "grade_2": 1, "grade_3": 2}
LOCATION_MAP = {"convexity": 0, "parasagittal": 1, "skull_base": 2,
                "sphenoid_wing": 3, "other": 4}

# Location similarity matrix (order matches LOCATION_MAP).
LOCATION_SIMILARITY = np.array([
    [1.0, 0.7, 0.4, 0.3, 0.5],
    [0.7, 1.0, 0.6, 0.4, 0.5],
    [0.4, 0.6, 1.0, 0.7, 0.5],
    [0.3, 0.4, 0.7, 1.0, 0.5],
    [0.5, 0.5, 0.5, 0.5, 1.0],
])

LOCATION_KEYWORDS = {
    "convexity": ["convexity", "convex"],
    "skull_base": ["skull base", "skull-base", "posterior fossa", "petrous",
                   "clivus", "cavernous", "sella", "sellar", "foramen magnum",
                   "tentorial", "cranial fossa", "petroclival", "cerebellopontine",
                   "olfactory groove", "cribriform", "tuberculum", "planum"],
    "parasagittal": ["parasagittal", "para-sagittal", "falx", "falc",
                     "interhemispheric", "sagittal sinus"],
    "sphenoid_wing": ["sphenoid wing", "sphenoidal wing", "clinoid",
                      "lesser wing", "greater wing", "sphenoid"],
    "other": ["intraventricular", "pineal", "orbital", "ventricle", "cpa"],
}


# ── Bucket functions ───────────────────────────────────────────────────────
def age_bucket(age: Optional[float]) -> str:
    if age is None:
        return "50-65"
    if age < 50:
        return "<50"
    if age <= 65:
        return "50-65"
    return ">=65"


def gender_bucket(gender: Optional[str]) -> str:
    if not gender:
        return "F"
    return "M" if str(gender).strip().upper().startswith("M") else "F"


def grade_bucket(text: Optional[str]) -> str:
    if not text:
        return "grade_1"
    t = str(text).lower()
    for g, kws in [
        ("grade_3", ["grade 3", "grade iii", "grade_3", "anaplastic",
                     "malignant", "who iii"]),
        ("grade_2", ["grade 2", "grade ii", "grade_2", "atypical", "who ii"]),
        ("grade_1", ["grade 1", "grade i", "grade_1", "benign",
                     "typical", "who i"]),
    ]:
        if any(k in t for k in kws):
            return g
    return "grade_1"


def location_bucket(text: Optional[str]) -> str:
    if not text:
        return "other"
    t = str(text).lower()
    for bucket, kws in LOCATION_KEYWORDS.items():
        if any(k in t for k in kws):
            return bucket
    return "other"


def size_bucket(size_cm: Optional[float]) -> Optional[str]:
    if size_cm is None:
        return None
    if size_cm < 2.0:
        return "small"
    if size_cm < 4.0:
        return "medium"
    return "large"


def speed_bucket(speed_cm_per_year: Optional[float]) -> str:
    if speed_cm_per_year is None:
        return "stable"
    mm = speed_cm_per_year * 10.0
    if mm < 2.0:
        return "stable"
    if mm < 5.0:
        return "slow_growth"
    return "fast_growth"


def action_of_event(event: dict) -> str:
    """Derive the clinical action represented by an event."""
    if event.get("surgery_performed"):
        return "surgery"
    if event.get("radiation_performed"):
        return "radiation"
    return "wait_and_watch"
