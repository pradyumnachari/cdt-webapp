"""
Evidence engine for cdt_webapp_v4 (descriptive, not prescriptive).

Performance-only, cohort-grounded. Runs entirely on the parsed CSV — no
pipeline, no LLM, no precomputed files. For each decision it produces TWO
complementary recommendations from level-matched, archetype-similar patients:

  A. Outcome-optimal  — argmax P(functional | action)       [recommend]
  B. Practice-based   — most frequent action at this stage  [practice_recommendation]

Both draw on the same pool: training patients who faced the SAME decision
level, weighted by archetype similarity (down-weighted on state mismatch),
one observation per patient.

Utility U(a) = P(functional | a).  Delta-U = U(best) - U(observed).
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

from . import buckets as B

# state-mismatch down-weight: a similar patient seen in a different
# (size, symptoms) state still informs the estimate, but less.
_STATE_MISMATCH_WEIGHT = 0.45

# distance weights per archetype axis
_W_AGE, _W_GENDER, _W_GRADE = 0.6, 1.0, 1.2


# ── archetype similarity ───────────────────────────────────────────────────
def archetype_similarity(a: dict, b: dict) -> float:
    """exp(-distance) in [0, 1]; 1.0 == identical archetype."""
    loc_sim = float(B.LOCATION_SIMILARITY[a["location"], b["location"]])
    dist = (
        _W_AGE * abs(a["age"] - b["age"])
        + _W_GENDER * (a["gender"] != b["gender"])
        + _W_GRADE * abs(a["grade"] - b["grade"])
        + (1.0 - loc_sim)
    )
    return math.exp(-dist)


def retrieve_similar(record: dict, train: Dict[str, dict],
                     k: int) -> List[dict]:
    """Top-k training patients by archetype similarity (excludes self)."""
    scored = []
    for pid, tp in train.items():
        if pid == record["patient_id"]:
            continue
        scored.append({
            "record": tp,
            "similarity": archetype_similarity(record["archetype"],
                                               tp["archetype"]),
        })
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:k]


# ── shared: level-matched similar observations ─────────────────────────────
def _level_observations(record: dict, level: int,
                        train: Dict[str, dict]) -> tuple:
    """
    Gather training patients who faced the SAME decision stage (level), one
    observation per patient.

    Restricting to the same level — rather than pooling every decision in a
    patient's trajectory — is what makes the estimate "what happened at THIS
    decision point". Each patient contributes once, so long trajectories no
    longer count multiple times.

    Returns (level_info, [ {pid, action, weight, status}, ... ]).
    """
    li = record["levels"].get(level)
    if li is None:
        raise ValueError(f"patient has no level {level}")
    target_arch = record["archetype"]
    target_state = li["state_key"]

    obs: List[dict] = []
    for pid, tp in train.items():
        if pid == record["patient_id"]:
            continue
        tl = tp["levels"].get(level)
        if tl is None:                       # never reached this stage
            continue
        sim = archetype_similarity(target_arch, tp["archetype"])
        w = sim * (1.0 if tl["state_key"] == target_state
                   else _STATE_MISMATCH_WEIGHT)
        obs.append({
            "pid": pid,
            "action": tl["action"],
            "weight": w,
            "status": tp["outcome"]["functional_status"],
        })
    return li, obs


# ── recommendation A: outcome-optimal ──────────────────────────────────────
def recommend(record: dict, level: int, train: Dict[str, dict]) -> dict:
    """
    OUTCOME-OPTIMAL recommendation: estimate P(functional | action) at this
    decision stage from level-matched, archetype-similar patients, and
    recommend the argmax.

    Returns: level, state_key, observed_action, best_action, p_by_action,
    n_eff_by_action, n_patients_by_action, support.
    """
    li, obs = _level_observations(record, level, train)

    weight: Dict[str, float] = {a: 0.0 for a in B.ACTIONS}
    func: Dict[str, float] = {a: 0.0 for a in B.ACTIONS}
    n_pat: Dict[str, int] = {a: 0 for a in B.ACTIONS}

    for o in obs:
        a = o["action"]
        if a not in weight:
            continue
        n_pat[a] += 1
        if o["status"] == "unknown":
            continue
        y = 1.0 if o["status"] == "functional" else 0.0
        weight[a] += o["weight"]
        func[a] += o["weight"] * y

    p_by_action: Dict[str, Optional[float]] = {}
    n_eff: Dict[str, float] = {}
    for a in B.ACTIONS:
        n_eff[a] = weight[a]
        p_by_action[a] = (func[a] / weight[a]) if weight[a] > 1e-9 else None

    supported = {a: p for a, p in p_by_action.items() if p is not None}
    if supported:
        best = max(supported, key=lambda a: (supported[a], n_eff[a]))
    else:
        best = li["action"]

    return {
        "level": level,
        "state_key": li["state_key"],
        "observed_action": li["action"],
        "best_action": best,
        "p_by_action": p_by_action,
        "n_eff_by_action": n_eff,
        "n_patients_by_action": n_pat,
        "support": sum(weight.values()),
    }


# ── recommendation B: practice-based ───────────────────────────────────────
def practice_recommendation(record: dict, level: int,
                            train: Dict[str, dict]) -> dict:
    """
    PRACTICE-BASED recommendation: the action most frequently chosen by
    level-matched, archetype-similar patients at this decision stage —
    independent of outcome.

    This complements `recommend()`: outcome-optimal says "what tends to work
    best", practice-based says "what clinicians actually did for patients
    like this". Agreement is a strong signal; divergence flags a case worth
    a closer look.

    Returns: level, state_key, observed_action, best_action, freq_by_action
    (similarity-weighted), count_by_action (raw patient counts), n_total.
    """
    li, obs = _level_observations(record, level, train)

    weight: Dict[str, float] = {a: 0.0 for a in B.ACTIONS}
    count: Dict[str, int] = {a: 0 for a in B.ACTIONS}
    for o in obs:
        a = o["action"]
        if a not in weight:
            continue
        weight[a] += o["weight"]
        count[a] += 1

    total = sum(weight.values())
    if total > 1e-9:
        freq = {a: w / total for a, w in weight.items()}
        best = max(freq, key=lambda a: (freq[a], count[a]))
    else:
        freq = {a: 0.0 for a in B.ACTIONS}
        best = li["action"]

    return {
        "level": level,
        "state_key": li["state_key"],
        "observed_action": li["action"],
        "best_action": best,
        "freq_by_action": freq,
        "count_by_action": count,
        "n_total": len(obs),
    }


def counterfactuals(record: dict, train: Dict[str, dict]) -> List[dict]:
    """Per-level observed-vs-optimal comparison with delta-U."""
    rows = []
    for level in sorted(record["levels"]):
        rec = recommend(record, level, train)
        prac = practice_recommendation(record, level, train)
        p = rec["p_by_action"]
        u_best = p.get(rec["best_action"]) or 0.0
        u_obs = p.get(rec["observed_action"])
        u_obs = u_obs if u_obs is not None else u_best
        rows.append({
            "level": level,
            "state_key": rec["state_key"],
            "observed": rec["observed_action"],
            "optimal": rec["best_action"],
            "practice": prac["best_action"],
            "u_optimal": u_best,
            "u_observed": u_obs,
            "delta_u": u_best - u_obs,
            "n_eff": rec["n_eff_by_action"].get(rec["best_action"], 0.0),
        })
    return rows


# ── cohort-level statistics (for the Cohort tab) ───────────────────────────
def cohort_stats(patients: Dict[str, dict]) -> dict:
    """Aggregate descriptive statistics over a (possibly filtered) cohort."""
    recs = list(patients.values())
    n = len(recs)
    known = [r for r in recs if r["outcome"]["functional_status"] != "unknown"]
    n_func = sum(r["outcome"]["functional_status"] == "functional"
                 for r in known)

    by_grade: Dict[str, List[int]] = {}
    for r in known:
        g = r["stratification"]["grade"]
        is_f = r["outcome"]["functional_status"] == "functional"
        by_grade.setdefault(g, []).append(int(is_f))

    by_first_action: Dict[str, List[int]] = {}
    for r in known:
        a = r["levels"].get(1, {}).get("action")
        if a is None:
            continue
        is_f = r["outcome"]["functional_status"] == "functional"
        by_first_action.setdefault(a, []).append(int(is_f))

    return {
        "n": n,
        "n_outcome_known": len(known),
        "n_functional": n_func,
        "functional_rate": (n_func / len(known)) if known else None,
        "by_grade": {g: (sum(v), len(v)) for g, v in sorted(by_grade.items())},
        "by_first_action": {a: (sum(v), len(v))
                            for a, v in by_first_action.items()},
    }


def quality_summary(patients: Dict[str, dict]) -> dict:
    """Aggregate data-quality flags across the cohort."""
    total_ev = total_cp = total_unc = total_inf = total_date = total_ext = 0
    n_genetic_patients = 0
    for r in patients.values():
        q = r["quality"]
        total_ev += q["n_events"]
        total_cp += q["n_copy_paste"]
        total_unc += q["n_uncertain"]
        total_inf += q["n_size_inferred"]
        total_date += q["n_date_flag"]
        total_ext += q["n_external"]
        n_genetic_patients += q["n_genetic"] > 0
    return {
        "total_events": total_ev,
        "copy_paste": total_cp,
        "uncertain": total_unc,
        "size_inferred": total_inf,
        "date_flag": total_date,
        "external": total_ext,
        "patients_with_genetic": n_genetic_patients,
    }


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple:
    """Wilson score 95% CI for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
