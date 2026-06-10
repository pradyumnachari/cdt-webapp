"""
Build a DEMO CSV in the real-data (v7) input format.

This lets cdt_webapp_v4 be exercised end-to-end before the real extraction
CSV is available. It converts the existing synthetic cohort into the exact
schema the real pipeline emits, so the app code does not need to change when
the real file is swapped in.

Output CSV columns
------------------
    patient_id   : str   patient / MRN identifier
    note_text    : str   short free-text note (demo placeholder)
    generation   : str   JSON string, schema below  <-- the "third column"

`generation` JSON schema (per patient)
--------------------------------------
    {
      "patient_demographics": {
        "age_at_diagnosis", "gender", "tumor_location",
        "diagnosis_institution", "pathology_grade"
      },
      "events": [ { event_number, months_since_diagnosis, tumor_size_cm,
        symptoms_present, pathology_grade, growth_velocity_cm_per_year,
        surgery_performed, radiation_performed, recurrence_detected,
        ecog_score, kps_score, copy_paste_suspected, event_type,
        institution, temporal_relation, date_consistency_flag,
        date_consistency_note, uncertain, nccn_domain,
        tumor_size_inferred, systemic, genetic_testing_flag } ]
    }

Source (synthetic, already in the repo)
    CDT_code/ground_truths_synth_v4/ground_truth.json   -- demographics, grade
    CDT_code/cache_notes_eval_final_notes_v2/<pid>_extraction.json -- visits

Run
    python tools/build_dummy_csv.py

Writes (created fresh; never overwrites anything)
    cdt_webapp_v4/data/dummy_cohort.csv
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
WEBAPP_DIR = Path(__file__).resolve().parents[1]          # cdt_webapp_v4/
REPO_ROOT = WEBAPP_DIR.parent                              # CDT_code/

GT_PATH = REPO_ROOT / "ground_truths_synth_v4" / "ground_truth.json"
EXTRACTION_DIR = REPO_ROOT / "cache_notes_eval_final_notes_v2"
OUT_CSV = WEBAPP_DIR / "data" / "dummy_cohort.csv"


# --------------------------------------------------------------------------
# Deterministic pseudo-random flags
# --------------------------------------------------------------------------
def _flag(pid: str, vn, salt: str, pct: int) -> bool:
    """Deterministic True for ~pct% of (patient, visit, salt) triples.

    Used to sprinkle realistic data-quality flags into the demo cohort so the
    app's data-quality panel has something to show. Real extraction data will
    carry these flags directly.
    """
    h = int(hashlib.md5(f"{pid}|{vn}|{salt}".encode()).hexdigest(), 16)
    return (h % 100) < pct


# --------------------------------------------------------------------------
# Event-level derivations
# --------------------------------------------------------------------------
def _event_type(v: dict) -> str:
    if v.get("surgery_performed"):
        return "surgery"
    if v.get("radiation_performed"):
        return "radiation"
    if v.get("tumor_size_cm") is not None:
        return "imaging"
    return "clinical_visit"


def _nccn_domain(idx: int, v: dict) -> str:
    if v.get("surgery_performed"):
        return "extent_of_resection"
    if idx == 0:
        return "initial_presentation_and_imaging"
    if v.get("recurrence_detected"):
        return "supportive_care_and_complications"
    if v.get("tumor_size_cm") is not None:
        return "surveillance_imaging"
    return "supportive_care_and_complications"


def _build_event(pid: str, idx: int, v: dict) -> dict:
    """Map one synthetic extraction visit -> one v7-schema event."""
    vn = v.get("visit_number", idx + 1)
    has_size = v.get("tumor_size_cm") is not None
    return {
        "event_number": vn,
        "months_since_diagnosis": v.get("months_since_diagnosis"),
        "tumor_size_cm": v.get("tumor_size_cm"),
        "symptoms_present": v.get("symptoms_present"),
        "pathology_grade": v.get("pathology_grade"),
        "growth_velocity_cm_per_year": v.get("growth_velocity_cm_per_year"),
        "surgery_performed": v.get("surgery_performed"),
        "radiation_performed": v.get("radiation_performed"),
        "recurrence_detected": bool(v.get("recurrence_detected", False)),
        "ecog_score": v.get("ecog_score"),
        "kps_score": v.get("kps_score"),
        "copy_paste_suspected": _flag(pid, vn, "cp", 8),
        "event_type": _event_type(v),
        "institution": "external" if _flag(pid, vn, "inst", 15) else "current",
        "temporal_relation": "at_this_encounter",
        "date_consistency_flag": _flag(pid, vn, "date", 5),
        "date_consistency_note": None,
        "uncertain": _flag(pid, vn, "unc", 7),
        "nccn_domain": _nccn_domain(idx, v),
        "tumor_size_inferred": has_size and _flag(pid, vn, "inf", 12),
        "systemic": False,
        "genetic_testing_flag": _flag(pid, vn, "gen", 4),
    }


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    if not GT_PATH.exists():
        raise SystemExit(f"Missing synthetic ground truth: {GT_PATH}")
    if not EXTRACTION_DIR.exists():
        raise SystemExit(f"Missing extraction cache dir: {EXTRACTION_DIR}")

    gt_records = json.loads(GT_PATH.read_text())
    gt_by_id = {r["patient_id"]: r for r in gt_records}

    rows = []
    for pid, gt in sorted(gt_by_id.items()):
        ext_path = EXTRACTION_DIR / f"{pid}_extraction.json"
        if not ext_path.exists():
            continue
        try:
            ext = json.loads(ext_path.read_text())
        except Exception:
            continue

        visits = ext.get("visits", [])
        if not visits:
            continue

        demo = gt.get("demographics", {})
        ext_demo = ext.get("patient_demographics", {})
        strat = gt.get("stratification", {})

        gender_raw = ext_demo.get("gender") or demo.get("sex") or ""
        gender = "Female" if str(gender_raw).upper().startswith("F") else "Male"

        patient_demographics = {
            "age_at_diagnosis": ext_demo.get("age_at_diagnosis") or demo.get("age"),
            "gender": gender,
            "tumor_location": ext_demo.get("tumor_location")
            or demo.get("tumor_location"),
            "diagnosis_institution": "Demo General Hospital",
            "pathology_grade": strat.get("grade", "grade_1"),
        }

        events = [_build_event(pid, i, v) for i, v in enumerate(visits)]

        generation = {
            "patient_demographics": patient_demographics,
            "events": events,
        }

        note_snippets = [
            v.get("notes") for v in visits if v.get("notes")
        ]
        note_text = " ".join(note_snippets[:4]) or "Synthetic demo note."

        rows.append({
            "patient_id": pid,
            "note_text": note_text,
            "generation": json.dumps(generation),
        })

    if not rows:
        raise SystemExit("No patients converted -- check source paths.")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["patient_id", "note_text", "generation"]).to_csv(
        OUT_CSV, index=False
    )
    print(f"Wrote {len(rows)} patients -> {OUT_CSV}")


if __name__ == "__main__":
    main()
