"""
Data layer for cdt_webapp_v4.

Reads ONE CSV (v7 format) and turns each row's `generation` JSON into a
self-contained patient record the UI pages consume. No dependency on the
heavy CDT pipeline packages — all derivation happens here.

v4 enriches the v3 patient record with fields required by the qa_v9 engine:
  - functional_status     (top-level mirror of outcome.functional_status)
  - action_sequence       (list of canonical actions across levels)
  - level_info            (qa_v9-shape: action, months_since_diagnosis,
                            tumor_size_cm, symptoms_present, surgery_performed,
                            radiation_performed)
  - v7_raw_events         (the normalized event list, preserved verbatim)

The v3 keys (events, levels, outcome, etc.) are kept unchanged so pages 1/2
continue to work.

Patient record shape
--------------------
    {
      "patient_id", "display_id", "split",
      "demographics":   {age, gender, location, grade, institution},
      "stratification": {age, gender, grade, location},      # string buckets
      "archetype":      {age, gender, grade, location},      # numeric codes
      "events":         [ normalized event dicts ],
      "levels":         { level_int -> v3 level_info },
      "max_level", "headline",
      "outcome":        {functional_status, ecog_score, kps_score},
      "quality":        {n_events, n_copy_paste, n_uncertain,
                         n_size_inferred, n_date_flag, n_external},
      # ── v4 additions for qa_v9 compatibility ──
      "functional_status": str,                              # top-level mirror
      "action_sequence":   [str, ...],                       # per-level actions
      "level_info":        { int -> {action, months_since_diagnosis,
                                     tumor_size_cm, symptoms_present,
                                     surgery_performed, radiation_performed} },
      "v7_raw_events":     [event dicts],                    # alias of events
    }
"""

from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional

import pandas as pd

from . import buckets as B
from .config import GENERATION_COLUMN, ID_COLUMNS, K_MAX_LEVELS, TEST_FRACTION


# ── small coercion helpers ─────────────────────────────────────────────────
def _f(v) -> Optional[float]:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v) -> Optional[int]:
    f = _f(v)
    return int(round(f)) if f is not None else None


def _b(v) -> bool:
    return bool(v) if v is not None else False


def _parse_generation(raw) -> Optional[dict]:
    """Parse the `generation` cell — handles dict or (fenced) JSON string."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, dict):
        return raw
    s = str(raw).strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


# ── event normalization ────────────────────────────────────────────────────
def _normalize_event(ev: dict, idx: int) -> dict:
    """Coerce one raw v7 event into typed fields the app relies on."""
    return {
        "event_number": _i(ev.get("event_number")) or (idx + 1),
        "months": _f(ev.get("months_since_diagnosis")),
        "tumor_size_cm": _f(ev.get("tumor_size_cm")),
        "symptoms_present": _b(ev.get("symptoms_present")),
        "pathology_grade": ev.get("pathology_grade"),
        "growth_velocity": _f(ev.get("growth_velocity_cm_per_year")),
        "surgery_performed": ev.get("surgery_performed"),
        "radiation_performed": ev.get("radiation_performed"),
        "recurrence_detected": _b(ev.get("recurrence_detected")),
        "ecog_score": _i(ev.get("ecog_score")),
        "kps_score": _i(ev.get("kps_score")),
        "event_type": ev.get("event_type"),
        "nccn_domain": ev.get("nccn_domain"),
        "institution": ev.get("institution") or "current",
        "temporal_relation": ev.get("temporal_relation"),
        # data-quality / provenance flags (new in real data)
        "copy_paste_suspected": _b(ev.get("copy_paste_suspected")),
        "uncertain": _b(ev.get("uncertain")),
        "tumor_size_inferred": _b(ev.get("tumor_size_inferred")),
        "date_consistency_flag": _b(ev.get("date_consistency_flag")),
        "date_consistency_note": ev.get("date_consistency_note"),
        "systemic": _b(ev.get("systemic")),
        "genetic_testing_flag": _b(ev.get("genetic_testing_flag")),
    }


def _state_key(ev: dict) -> tuple:
    """(size_bucket, symptoms) for a normalized event."""
    sz = B.size_bucket(ev["tumor_size_cm"]) or "medium"
    symp = "present" if ev["symptoms_present"] else "none"
    return sz, symp


# ── level derivation (replaces GT trajectory for real data) ────────────────
def _derive_levels(events: List[dict]) -> Dict[int, dict]:
    """
    Build decision levels from action epochs.

    The real data has no ground-truth trajectory, so the observed action
    sequence is derived directly from the events (surgery/radiation fields).
    Consecutive same-action events form an "epoch"; each epoch up to
    K_MAX_LEVELS becomes a decision level.
    """
    if not events:
        return {}

    epochs: List[dict] = []
    for ev in events:
        act = B.action_of_event(ev)
        if not epochs or epochs[-1]["action"] != act:
            epochs.append({"action": act, "events": [ev]})
        else:
            epochs[-1]["events"].append(ev)

    levels: Dict[int, dict] = {}
    for lvl, ep in enumerate(epochs[:K_MAX_LEVELS], start=1):
        first, last = ep["events"][0], ep["events"][-1]
        size, symp = _state_key(first)
        levels[lvl] = {
            "state_key": f"{size}_{symp}",
            "size_bucket": size,
            "symptoms": symp,
            "action": ep["action"],
            "first_event": first["event_number"],
            "last_event": last["event_number"],
        }
    return levels


# ── outcome derivation (performance-only) ──────────────────────────────────
def _derive_outcome(events: List[dict]) -> dict:
    """
    Functional status from the last event with a performance score.

    ECOG 0-2 (or KPS >= 70) -> functional; else impaired. Real data is
    performance-only — no survival outcome is computed.
    """
    ecog = kps = None
    for ev in reversed(events):
        if ev["ecog_score"] is not None:
            ecog = ev["ecog_score"]
            kps = ev["kps_score"]
            break
        if ev["kps_score"] is not None and kps is None:
            kps = ev["kps_score"]

    status = "unknown"
    if ecog is not None:
        status = "functional" if ecog <= 2 else "impaired"
    elif kps is not None:
        status = "functional" if kps >= 70 else "impaired"

    return {"functional_status": status, "ecog_score": ecog, "kps_score": kps}


def _archetype(strat: dict) -> dict:
    return {
        "age": B.AGE_MAP.get(strat["age"], 1),
        "gender": B.GENDER_MAP.get(strat["gender"], 1),
        "grade": B.GRADE_MAP.get(strat["grade"], 0),
        "location": B.LOCATION_MAP.get(strat["location"], 4),
    }


def _headline(demo: dict, strat: dict) -> str:
    age = demo.get("age")
    age_s = f"{int(age)}-year-old" if age else "Patient,"
    sex = "woman" if strat["gender"] == "F" else "man"
    grade = strat["grade"].replace("_", " ")
    loc = strat["location"].replace("_", " ")
    return f"{age_s} {sex}, {grade} {loc} meningioma"


# ── per-patient builder ────────────────────────────────────────────────────
def _build_patient(pid: str, gen: dict) -> Optional[dict]:
    demo_raw = gen.get("patient_demographics") or {}
    raw_events = gen.get("events") or []

    events = [_normalize_event(e, i) for i, e in enumerate(raw_events)]
    # keep only post-diagnosis events, ordered by time
    events = [e for e in events if e["months"] is not None]
    events.sort(key=lambda e: (e["months"], e["event_number"]))
    if not events:
        return None

    grade_src = demo_raw.get("pathology_grade")
    if not grade_src:
        for e in events:
            if e["pathology_grade"]:
                grade_src = e["pathology_grade"]
                break

    location_src = demo_raw.get("tumor_location")

    strat = {
        "age": B.age_bucket(_f(demo_raw.get("age_at_diagnosis"))),
        "gender": B.gender_bucket(demo_raw.get("gender")),
        "grade": B.grade_bucket(grade_src),
        "location": B.location_bucket(location_src),
    }
    demographics = {
        "age": _f(demo_raw.get("age_at_diagnosis")),
        "gender": demo_raw.get("gender"),
        "location": location_src,
        "grade": grade_src,
        "institution": demo_raw.get("diagnosis_institution"),
    }

    levels = _derive_levels(events)
    if not levels:
        return None

    # v4 additions for qa_v9 engine ───────────────────────────────────────
    # Build level_info in qa_v9 shape (continuous fields preserved per level)
    level_info = {}
    for lv, li in levels.items():
        # First event of the epoch carries the snapshot at the decision point
        first_ev = next((e for e in events
                        if e["event_number"] == li["first_event"]), None)
        # Surgery/radiation subtype: search across the epoch's events
        epoch_events = [e for e in events
                       if li["first_event"] <= e["event_number"] <= li["last_event"]]
        surg_extent = next((e["surgery_performed"] for e in epoch_events
                           if e["surgery_performed"]), None)
        rad_mod = next((e["radiation_performed"] for e in epoch_events
                       if e["radiation_performed"]), None)
        level_info[lv] = {
            "action": li["action"],
            "months_since_diagnosis": (first_ev["months"]
                                      if first_ev and first_ev["months"] is not None
                                      else None),
            "tumor_size_cm": (first_ev["tumor_size_cm"]
                             if first_ev and first_ev["tumor_size_cm"] is not None
                             else None),
            "symptoms_present": (first_ev["symptoms_present"]
                                if first_ev else None),
            "surgery_performed": surg_extent,
            "radiation_performed": rad_mod,
            "state_key": li["state_key"],
            "size_bucket": li["size_bucket"],
        }

    action_sequence = [levels[lv]["action"] for lv in sorted(levels)]
    outcome_d = _derive_outcome(events)

    quality = {
        "n_events": len(events),
        "n_copy_paste": sum(e["copy_paste_suspected"] for e in events),
        "n_uncertain": sum(e["uncertain"] for e in events),
        "n_size_inferred": sum(e["tumor_size_inferred"] for e in events),
        "n_date_flag": sum(e["date_consistency_flag"] for e in events),
        "n_external": sum(e["institution"] == "external" for e in events),
        "n_genetic": sum(e["genetic_testing_flag"] for e in events),
    }

    return {
        "patient_id": str(pid),
        "display_id": str(pid),
        "demographics": demographics,
        "stratification": strat,
        "archetype": _archetype(strat),
        "events": events,
        "levels": levels,
        "max_level": len(levels),
        "headline": _headline(demographics, strat),
        "outcome": outcome_d,
        "quality": quality,
        # ── v4 additions for qa_v9 compatibility ──
        "functional_status": outcome_d["functional_status"],
        "action_sequence": action_sequence,
        "level_info": level_info,
        "v7_raw_events": events,  # alias — qa_v9 expects this key
    }


def _assign_split(pid: str) -> str:
    """Deterministic train/test split (real data carries no split column)."""
    h = int(hashlib.md5(f"split|{pid}".encode()).hexdigest(), 16)
    return "test" if (h % 1000) < int(TEST_FRACTION * 1000) else "train"


# ── public API ─────────────────────────────────────────────────────────────
def load_cohort(csv_path) -> dict:
    """
    Load and normalize the cohort CSV.

    Returns {"patients": {pid->record}, "train": {...}, "test": {...},
             "errors": [pid,...]}.
    """
    # dtype=str preserves zero-padded / non-numeric identifiers (e.g. "0001",
    # MRN strings) — pandas would otherwise coerce them to integers.
    df = pd.read_csv(csv_path, dtype=str)

    id_col = next((c for c in ID_COLUMNS if c in df.columns), None)
    if id_col is None:
        raise ValueError(
            f"CSV must contain one of {ID_COLUMNS}; found {list(df.columns)}"
        )
    if GENERATION_COLUMN not in df.columns:
        raise ValueError(
            f"CSV must contain a '{GENERATION_COLUMN}' column; "
            f"found {list(df.columns)}"
        )

    patients: Dict[str, dict] = {}
    errors: List[str] = []
    for _, row in df.iterrows():
        pid = str(row[id_col])
        gen = _parse_generation(row[GENERATION_COLUMN])
        if gen is None:
            errors.append(pid)
            continue
        rec = _build_patient(pid, gen)
        if rec is None:
            errors.append(pid)
            continue
        rec["split"] = _assign_split(pid)
        patients[pid] = rec

    train = {p: r for p, r in patients.items() if r["split"] == "train"}
    test = {p: r for p, r in patients.items() if r["split"] == "test"}
    return {"patients": patients, "train": train, "test": test, "errors": errors}


def reconstruct_note(record: dict, up_to_level: Optional[int] = None) -> str:
    """
    Build a readable note from structured events (real data has no free
    note text per event). Truncated at the given decision level.
    """
    cutoff = 10 ** 9
    if up_to_level is not None:
        li = record["levels"].get(up_to_level)
        if li:
            cutoff = li["last_event"]

    lines = []
    for ev in record["events"]:
        if ev["event_number"] > cutoff:
            break
        parts = [f"**Event {ev['event_number']}**"]
        if ev["months"] is not None:
            parts.append(f"(+{ev['months']:.1f} mo)")
        if ev["event_type"]:
            parts.append(f"· {ev['event_type'].replace('_', ' ')}")
        if ev["tumor_size_cm"] is not None:
            inf = " (inferred)" if ev["tumor_size_inferred"] else ""
            parts.append(f"| Tumor {ev['tumor_size_cm']:.1f} cm{inf}")
        parts.append(f"| Symptoms: {'yes' if ev['symptoms_present'] else 'none'}")
        if ev["ecog_score"] is not None:
            parts.append(f"| ECOG {ev['ecog_score']}")
        if ev["surgery_performed"]:
            parts.append(f"| Surgery: {ev['surgery_performed']}")
        if ev["radiation_performed"]:
            parts.append(f"| Radiation: {ev['radiation_performed']}")
        if ev["recurrence_detected"]:
            parts.append("| **Recurrence**")
        flags = []
        if ev["copy_paste_suspected"]:
            flags.append("copy-paste suspected")
        if ev["uncertain"]:
            flags.append("uncertain")
        if ev["date_consistency_flag"]:
            flags.append("date inconsistency")
        if flags:
            parts.append(f"  _[{', '.join(flags)}]_")
        lines.append(" ".join(parts))
    return "\n\n".join(lines) if lines else "_No event data._"
