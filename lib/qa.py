"""
qa_v9 engine for cdt_webapp_v4.

Self-contained port of qa_v9_core + qa_v9_handlers (from notebook 4.12),
adapted for the webapp:
  - LLM transport: OpenAI SDK (gpt-4o), api_key threaded explicitly.
  - Patient records: webapp data_loader output (includes level_info,
    action_sequence, functional_status, v7_raw_events).
  - Public API: answer_question(question, patients, api_key) -> structured
    answer dict matching the screenshot panels.

Pipeline (4 LLM calls per question, except COMPOUND which recurses):
    question --LLM router-->     plan (JSON, 9 qtypes + COMPOUND)
    plan + cohort --executor-->  structured stats block (deterministic)
    block --LLM interpretation--> paragraph (numbers locked from block)
    block --LLM caveats-->        additional caveats (locked + LLM)
    answer --LLM responsivity-->  rewritten direct_answer
"""

from __future__ import annotations

import json
import math
import random
import re
import statistics as _stats_std
import time as _time
from collections import Counter as _Counter, defaultdict as _defaultdict
from typing import Dict, List, Optional

from scipy import stats as _scipy_stats

try:
    from sklearn.linear_model import LogisticRegression as _SkLR  # noqa: F401
    _HAS_SKLEARN = True
except Exception:
    _HAS_SKLEARN = False


# =====================================================================
# Constants
# =====================================================================

LLM_MODEL = "gpt-4o"
ROUTER_MAX_TOKENS = 1200
SYNTH_MAX_TOKENS = 800
ROUTER_TEMPERATURE = 0.0
SYNTH_TEMPERATURE = 0.0

RELIABILITY_THRESHOLDS = {"adequate": 50, "limited": 15, "underpowered": 3}
STRATIFIERS = ["grade", "age", "location"]
BASELINE_FEATURES = [
    ("Tumor size at L1 (cm)", "size_at_l1_cm",     "continuous"),
    ("Symptomatic at L1",     "symptomatic_at_l1", "binary"),
    ("Age (years)",           "age_years",         "continuous"),
    ("Location bucket",       "location",          "categorical"),
    ("Gender",                "gender",            "binary_mf"),
    ("WHO grade",             "grade",             "categorical"),
]
SMD_IMBALANCED_THRESHOLD = 0.10
SMD_SUBSTANTIAL_THRESHOLD = 0.25

VERIFIER_TOLERANCES = {
    "percentage_pp": 0.5, "risk_ratio": 0.02,
    "fishers_p": 0.005, "evalue": 0.05, "count_exact": True,
}
MDE_ALPHA = 0.05
MDE_POWER = 0.80
RELIABILITY_LEGEND = "Adequate (>=50/arm); Limited (15-49); Underpowered (3-14); Suppressed (<3)."

GLOSSES = {
    "cohort_construction":
        "Each row narrows the analytic population by one inclusion criterion. "
        "Sharp drops mark where generalizability is most constrained.",
    "outcomes_table":
        "Rate is the proportion of patients in this arm who maintained functional "
        "status. The 95% confidence interval (Clopper-Pearson exact binomial) "
        "is the range in which the true rate is expected to lie with 95% confidence.",
    "comparison_summary":
        "Absolute difference is arm-A rate minus arm-B rate, in percentage points. "
        "Risk ratio (RR) is the ratio of the two rates: RR > 1 favours arm A. "
        "Fisher's exact p is the probability of seeing a difference this large "
        "under the assumption that the two arms truly have the same rate.",
    "evalue":
        "E-value measures how strong an unmeasured confounder would have to be "
        "(on the risk-ratio scale) to fully explain away the observed effect.",
    "subgroup_detail":
        "The comparison is re-run within each stratum. The Reliability column "
        "indicates how seriously to take each row.",
    "baseline_differences":
        "Standardized mean difference (SMD): SMD<0.10 well balanced; 0.10-0.25 "
        "mild imbalance; >0.25 substantial imbalance.",
    "adjusted_analysis":
        "Multi-covariate inverse-probability weighting (IPW). The adjusted "
        "contrast is short of identified causal effect because no sensitivity "
        "analysis under unmeasured confounding is performed.",
    "reliability_legend": RELIABILITY_LEGEND,
}


# =====================================================================
# Statistical core (Clopper-Pearson, Fisher, CMH, MDE, bootstrap, E-value)
# =====================================================================

def assign_reliability(n_a, n_b):
    n_min = min(int(n_a), int(n_b))
    if n_min < RELIABILITY_THRESHOLDS["underpowered"]:
        return {"tag": "Suppressed", "suppressed": True}
    if n_min < RELIABILITY_THRESHOLDS["limited"]:
        return {"tag": "Underpowered", "suppressed": False}
    if n_min < RELIABILITY_THRESHOLDS["adequate"]:
        return {"tag": "Limited", "suppressed": False}
    return {"tag": "Adequate", "suppressed": False}


def clopper_pearson(k, n, alpha=0.05):
    k, n = int(k), int(n)
    if n <= 0: return (0.0, 0.0)
    lo = 0.0 if k == 0 else float(_scipy_stats.beta.ppf(alpha/2, k, n-k+1))
    hi = 1.0 if k == n else float(_scipy_stats.beta.ppf(1-alpha/2, k+1, n-k))
    return (lo, hi)


def _rr_ci(a_event, a_n, b_event, b_n, alpha=0.05):
    a_event, a_n = int(a_event), int(a_n)
    b_event, b_n = int(b_event), int(b_n)
    if a_n == 0 or b_n == 0:
        return (float("nan"), float("nan"), float("nan"))
    if a_event == 0 or b_event == 0 or a_event == a_n or b_event == b_n:
        ae, at, be, bt = a_event+0.5, a_n+1.0, b_event+0.5, b_n+1.0
    else:
        ae, at, be, bt = a_event, a_n, b_event, b_n
    rr = (ae/at) / (be/bt)
    var = 1.0/ae - 1.0/at + 1.0/be - 1.0/bt
    if var <= 0: return (float(rr), float("nan"), float("nan"))
    se = math.sqrt(var)
    z = _scipy_stats.norm.ppf(1-alpha/2)
    lr = math.log(rr)
    return (float(rr), float(math.exp(lr - z*se)), float(math.exp(lr + z*se)))


def _abs_diff_ci(a_event, a_n, b_event, b_n, alpha=0.05):
    if a_n == 0 or b_n == 0: return (0.0, float("nan"), float("nan"))
    p_a, p_b = a_event/a_n, b_event/b_n
    d = p_a - p_b
    var = p_a*(1-p_a)/a_n + p_b*(1-p_b)/b_n
    se = math.sqrt(var) if var > 0 else 0.0
    z = _scipy_stats.norm.ppf(1-alpha/2)
    return (float(d*100), float((d-z*se)*100), float((d+z*se)*100))


def _outcome_of(record, outcome_key="functional_status", success="functional"):
    v = record.get(outcome_key)
    if v is not None: return v
    if isinstance(record.get("outcome"), dict):
        return record["outcome"].get(outcome_key)
    return None


def fisher_and_effect(group_a, group_b, outcome_key="functional_status",
                      success="functional", arm_a_label="A", arm_b_label="B"):
    def _ct(records):
        n = len(records)
        k = sum(1 for r in records if _outcome_of(r, outcome_key, success) == success)
        return n, k
    n_a, k_a = _ct(group_a)
    n_b, k_b = _ct(group_b)
    ci_a = clopper_pearson(k_a, n_a)
    ci_b = clopper_pearson(k_b, n_b)
    rate_a = (k_a / n_a) if n_a > 0 else 0.0
    rate_b = (k_b / n_b) if n_b > 0 else 0.0
    rows = [
        {"arm": arm_a_label, "N": n_a, "n_functional": k_a,
         "rate_pct": round(rate_a*100, 1),
         "ci_pct": (round(ci_a[0]*100, 1), round(ci_a[1]*100, 1))},
        {"arm": arm_b_label, "N": n_b, "n_functional": k_b,
         "rate_pct": round(rate_b*100, 1),
         "ci_pct": (round(ci_b[0]*100, 1), round(ci_b[1]*100, 1))},
    ]
    if n_a > 0 and n_b > 0:
        try:
            _, fp = _scipy_stats.fisher_exact([[k_a, n_a-k_a], [k_b, n_b-k_b]])
        except Exception:
            fp = float("nan")
    else:
        fp = float("nan")
    rr, rr_lo, rr_hi = _rr_ci(k_a, n_a, k_b, n_b)
    dpp, dlo, dhi = _abs_diff_ci(k_a, n_a, k_b, n_b)
    _r1 = lambda x: None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x, 1)
    _r2 = lambda x: None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x, 2)
    _r3 = lambda x: None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x, 3)
    return rows, {
        "n_a": n_a, "n_b": n_b, "k_a": k_a, "k_b": k_b,
        "rate_a_pct": _r1(rate_a*100), "rate_b_pct": _r1(rate_b*100),
        "abs_diff_pp": _r1(dpp), "abs_diff_ci_pp": (_r1(dlo), _r1(dhi)),
        "rr": _r2(rr), "rr_ci": (_r2(rr_lo), _r2(rr_hi)),
        "fishers_exact_p": _r3(fp),
    }


def compute_evalue(rr, rr_ci_low=None, rr_ci_high=None):
    def _e(r):
        if r is None or (isinstance(r, float) and math.isnan(r)) or r <= 0:
            return None
        if r >= 1: return r + math.sqrt(r*(r-1))
        ri = 1.0/r
        return ri + math.sqrt(ri*(ri-1))
    pt = _e(rr)
    bd = None
    if rr is not None and not (isinstance(rr, float) and math.isnan(rr)):
        if (rr_ci_low is not None and rr_ci_high is not None
                and not (isinstance(rr_ci_low, float) and math.isnan(rr_ci_low))
                and not (isinstance(rr_ci_high, float) and math.isnan(rr_ci_high))):
            b = (rr_ci_low if rr >= 1 and rr_ci_low > 1 else
                 rr_ci_high if rr < 1 and rr_ci_high < 1 else 1.0)
            bd = _e(b)
    return {"evalue_point": round(pt, 2) if pt is not None else None,
            "evalue_ci_bound": round(bd, 2) if bd is not None else None}


def cochran_mantel_haenszel(stratum_counts):
    valid = [s for s in stratum_counts if s["a_n"] > 0 and s["b_n"] > 0]
    if not valid:
        return {"mh_or": None, "mh_or_ci": (None, None),
                "chi2": None, "p_value": None, "strata_used": 0}
    num_or = den_or = 0.0
    num_chi = var_chi = 0.0
    for s in valid:
        a, c = s["a_event"], s["a_n"] - s["a_event"]
        b, d = s["b_event"], s["b_n"] - s["b_event"]
        N = a + b + c + d
        if N == 0: continue
        num_or += (a*d)/N
        den_or += (b*c)/N
        a_exp = (a+b)*(a+c)/N
        num_chi += a - a_exp
        if N > 1:
            var_chi += ((a+b)*(c+d)*(a+c)*(b+d)) / (N*N*(N-1))
    mh_or = num_or/den_or if den_or > 0 else None
    chi2 = (num_chi**2)/var_chi if var_chi > 0 else None
    pv = (1.0 - float(_scipy_stats.chi2.cdf(chi2, df=1))) if chi2 is not None else None
    rbg_num = rbg_dl = rbg_dr = 0.0
    for s in valid:
        a, c = s["a_event"], s["a_n"] - s["a_event"]
        b, d = s["b_event"], s["b_n"] - s["b_event"]
        N = a + b + c + d
        if N == 0: continue
        rbg_num += (((a+d)/N)*((a*d)/N) + ((b+c)/N)*((b*c)/N))/2
        rbg_dl += (a*d)/N
        rbg_dr += (b*c)/N
    if mh_or is not None and mh_or > 0 and rbg_dl > 0 and rbg_dr > 0:
        var = rbg_num / (rbg_dl * rbg_dr)
        if var > 0:
            se = math.sqrt(var)
            z = _scipy_stats.norm.ppf(0.975)
            ci = (math.exp(math.log(mh_or)-z*se), math.exp(math.log(mh_or)+z*se))
        else:
            ci = (None, None)
    else:
        ci = (None, None)
    return {
        "mh_or": round(mh_or, 2) if mh_or is not None else None,
        "mh_or_ci": (round(ci[0], 2), round(ci[1], 2)) if ci[0] is not None else (None, None),
        "chi2": round(chi2, 3) if chi2 is not None else None,
        "p_value": round(pv, 4) if pv is not None else None,
        "strata_used": len(valid),
    }


def compute_mde(n_a, n_b, baseline_rate=None, alpha=MDE_ALPHA, power=MDE_POWER):
    if n_a < 1 or n_b < 1: return None
    p_b = baseline_rate if baseline_rate is not None else 0.50
    p_b = max(0.05, min(0.95, p_b))
    z_a = _scipy_stats.norm.ppf(1-alpha/2)
    z_b = _scipy_stats.norm.ppf(power)
    se = math.sqrt(p_b*(1-p_b)*(1.0/n_a + 1.0/n_b))
    return round((z_a + z_b) * se * 100, 1)


def bootstrap_ratio_ci(group_a, group_b, weights_a, weights_b,
                       outcome_key="functional_status", success="functional",
                       B=500, alpha=0.05, seed=0):
    rng = random.Random(seed)
    n_a, n_b = len(group_a), len(group_b)
    if n_a == 0 or n_b == 0: return (None, None)
    def _wr(recs, ws):
        num = den = 0.0
        for r, w in zip(recs, ws):
            if w <= 0: continue
            den += w
            if _outcome_of(r, outcome_key, success) == success: num += w
        return num/den if den > 0 else None
    rrs = []
    for _ in range(B):
        ia = [rng.randrange(n_a) for _ in range(n_a)]
        ib = [rng.randrange(n_b) for _ in range(n_b)]
        ra = _wr([group_a[i] for i in ia], [weights_a[i] for i in ia])
        rb = _wr([group_b[i] for i in ib], [weights_b[i] for i in ib])
        if ra is None or rb is None or rb == 0: continue
        rrs.append(ra/rb)
    if not rrs: return (None, None)
    rrs.sort()
    return (round(rrs[int((alpha/2)*len(rrs))], 2),
            round(rrs[int((1-alpha/2)*len(rrs)) - 1], 2))


# =====================================================================
# Feature extraction
# =====================================================================

def extract_feature(patient, feature_key):
    strat = patient.get("stratification") or {}
    if feature_key == "grade": return strat.get("grade")
    if feature_key == "gender": return strat.get("gender")
    if feature_key == "location": return strat.get("location")
    if feature_key == "age_years":
        for k in ("age_at_diagnosis", "age_years", "age"):
            v = patient.get(k)
            if v is not None and not isinstance(v, str):
                try: return float(v)
                except Exception: pass
        # webapp records carry demographics.age (continuous)
        v = (patient.get("demographics") or {}).get("age")
        if v is not None:
            try: return float(v)
            except Exception: pass
        return {"<50": 40.0, "50-65": 57.0, ">=65": 72.0}.get(strat.get("age"))
    if feature_key == "size_at_l1_cm":
        li = patient.get("level_info") or {}
        for lv in (1, "1"):
            entry = li.get(lv)
            if isinstance(entry, dict):
                v = entry.get("tumor_size_cm")
                if v is not None:
                    try: return float(v)
                    except Exception: pass
                b = entry.get("size_bucket")
                m = {"small": 1.5, "medium": 3.0, "large": 5.0}.get(b)
                if m is not None: return m
        for k in ("v7_raw_events", "events", "visits"):
            seq = patient.get(k) or []
            for ev in seq:
                if isinstance(ev, dict):
                    v = ev.get("tumor_size_cm")
                    if v is not None:
                        try: return float(v)
                        except Exception: pass
        return None
    if feature_key == "symptomatic_at_l1":
        li = patient.get("level_info") or {}
        for lv in (1, "1"):
            entry = li.get(lv)
            if isinstance(entry, dict):
                s = entry.get("symptoms_present")
                if isinstance(s, bool): return 1 if s else 0
                s2 = entry.get("symptoms")
                if isinstance(s2, str):
                    return 1 if s2.lower() in ("present","yes","true","symptomatic") else 0
        return None
    return None


# =====================================================================
# Baseline balance
# =====================================================================

def _smd_continuous(va, vb):
    va = [v for v in va if v is not None]; vb = [v for v in vb if v is not None]
    if len(va) < 2 or len(vb) < 2: return None
    ma, mb = _stats_std.mean(va), _stats_std.mean(vb)
    sa = _stats_std.stdev(va) if len(va) > 1 else 0.0
    sb = _stats_std.stdev(vb) if len(vb) > 1 else 0.0
    pooled = math.sqrt((sa**2 + sb**2)/2.0) if (sa or sb) else 0.0
    return 0.0 if pooled == 0 else float(abs(ma-mb)/pooled)


def _smd_binary(va, vb):
    va = [v for v in va if v is not None]; vb = [v for v in vb if v is not None]
    if not va or not vb: return None
    p_a, p_b = sum(va)/len(va), sum(vb)/len(vb)
    p_bar = (p_a + p_b)/2.0
    d = math.sqrt(p_bar*(1-p_bar))
    return 0.0 if d == 0 else float(abs(p_a-p_b)/d)


def _smd_categorical(va, vb):
    va = [v for v in va if v is not None]; vb = [v for v in vb if v is not None]
    if not va or not vb: return None
    levels = set(va) | set(vb)
    smds = [_smd_binary([1 if v == l else 0 for v in va],
                       [1 if v == l else 0 for v in vb]) for l in levels]
    smds = [s for s in smds if s is not None]
    return max(smds) if smds else None


def _continuous_summary(values, q_threshold=5):
    vs = sorted(v for v in values if v is not None)
    if not vs: return "-"
    if len(set(vs)) < q_threshold:
        c = _Counter(vs)
        return "; ".join(f"{v:.1f}: {n}" for v, n in c.most_common(3))
    med = _stats_std.median(vs)
    q1 = vs[max(0, int(len(vs)*0.25)-1)]
    q3 = vs[min(len(vs)-1, int(len(vs)*0.75))]
    return f"{med:.1f} (IQR {q1:.1f}-{q3:.1f})"


def _binary_summary(values):
    vs = [v for v in values if v is not None]
    if not vs: return "-"
    k = sum(vs)
    return f"{(k/len(vs))*100:.0f}% ({k}/{len(vs)})"


def _categorical_summary(values):
    vs = [v for v in values if v is not None]
    if not vs: return "-"
    return "; ".join(f"{k}: {v}" for k, v in _Counter(vs).most_common(3))


def compute_baseline_balance(group_a, group_b, arm_a_label="A", arm_b_label="B",
                             features=BASELINE_FEATURES):
    rows = []
    ak, bk = f"arm_{arm_a_label}", f"arm_{arm_b_label}"
    for display, key, ftype in features:
        va = [extract_feature(p, key) for p in group_a]
        vb = [extract_feature(p, key) for p in group_b]
        if ftype == "continuous":
            a_s, b_s = _continuous_summary(va), _continuous_summary(vb)
            smd = _smd_continuous(va, vb)
        elif ftype == "binary":
            a_s, b_s = _binary_summary(va), _binary_summary(vb)
            smd = _smd_binary(va, vb)
        elif ftype == "binary_mf":
            va_b = [1 if v == "F" else (0 if v == "M" else None) for v in va]
            vb_b = [1 if v == "F" else (0 if v == "M" else None) for v in vb]
            a_s = f"F: {sum(1 for v in va_b if v == 1)}; M: {sum(1 for v in va_b if v == 0)}"
            b_s = f"F: {sum(1 for v in vb_b if v == 1)}; M: {sum(1 for v in vb_b if v == 0)}"
            smd = _smd_binary(va_b, vb_b)
        else:
            a_s, b_s = _categorical_summary(va), _categorical_summary(vb)
            smd = _smd_categorical(va, vb)
        sr = round(smd, 2) if smd is not None else None
        rows.append({"feature": display, ak: a_s, bk: b_s, "smd": sr,
                    "imbalanced": bool(smd is not None and smd > SMD_IMBALANCED_THRESHOLD),
                    "substantial": bool(smd is not None and smd > SMD_SUBSTANTIAL_THRESHOLD)})
    return rows


# =====================================================================
# Cohort funnel + follow-up + modality
# =====================================================================

class CohortFunnel:
    def __init__(self, total_label="Total cohort", total_n=None):
        self.steps = []
        self._prev = None
        if total_n is not None:
            self.steps.append({"step_description": total_label,
                              "N": int(total_n), "delta_from_prev": None})
            self._prev = int(total_n)
    def record(self, label, n):
        n = int(n)
        d = (n - self._prev) if self._prev is not None else None
        self.steps.append({"step_description": label, "N": n, "delta_from_prev": d})
        self._prev = n
    def as_dict(self):
        return {"gloss": GLOSSES["cohort_construction"], "rows": list(self.steps)}


def compute_followup_range(cohort):
    times = []
    for p in cohort:
        events = p.get("v7_raw_events") or p.get("events") or []
        m = [e.get("months") for e in events
             if isinstance(e, dict) and e.get("months") is not None]
        if m: times.append(max(float(t) for t in m))
    if not times: return None
    return {"min_months": round(min(times), 1), "max_months": round(max(times), 1),
            "median_months": round(_stats_std.median(times), 1)}


def compute_modality_breakdown(cohort):
    counts = _Counter()
    for p in cohort:
        seen = set()
        for ev in (p.get("v7_raw_events") or p.get("events") or []):
            if isinstance(ev, dict) and ev.get("radiation_performed"):
                seen.add(ev["radiation_performed"])
        for m in seen: counts[m] += 1
    return dict(counts)


# =====================================================================
# LLM transport (OpenAI SDK)
# =====================================================================

def _llm(system, user, api_key, max_tokens=SYNTH_MAX_TOKENS,
         temperature=SYNTH_TEMPERATURE, json_mode=True, model=None):
    import openai
    model = model or LLM_MODEL
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    if hasattr(openai, "OpenAI"):
        client = openai.OpenAI(api_key=api_key)
        kwargs = {"model": model, "messages": messages,
                 "temperature": temperature, "max_tokens": max_tokens}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""
    openai.api_key = api_key
    resp = openai.ChatCompletion.create(
        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens,
    )
    return resp["choices"][0]["message"]["content"] or ""


def _llm_json(system, user, api_key, max_tokens=SYNTH_MAX_TOKENS,
              temperature=SYNTH_TEMPERATURE):
    try:
        raw = _llm(system, user, api_key, max_tokens=max_tokens,
                  temperature=temperature, json_mode=True)
    except Exception as e:
        return {"_error": f"llm_call_failed: {e}"}
    if not raw: return {"_error": "empty"}
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    s = m.group(0) if m else raw
    try:
        return json.loads(s)
    except Exception as e:
        s2 = re.sub(r"```json\s*|\s*```", "", s).strip()
        try: return json.loads(s2)
        except Exception:
            return {"_error": f"json_decode_failed: {e}", "_raw": raw[:400]}


# =====================================================================
# LLM ROUTER
# =====================================================================

ROUTER_SYSTEM_PROMPT = """You are the QUESTION TYPE ROUTER for a clinical
decision support system answering meningioma questions. You are a PARSER, not
a statistician. You NEVER emit numbers; you only translate the question into a
typed JSON plan.

Output VALID JSON:

{
  "qtype": "FACTUAL" | "DESCRIPTIVE" | "DESCRIPTIVE-TEMPORAL" | "COMPARATIVE" |
           "SUBGROUP-COMPARATIVE" | "TRAJECTORY" | "TEMPORAL-CONDITIONAL" |
           "PATHWAY-FUNNEL" | "COMPARATIVE-ADJUSTED" | "COMPOUND",
  "base_filter": {
      "grade": "grade_1"|"grade_2"|"grade_3"|null,
      "location": ["convexity"|"skull_base"|"parasagittal"|"sphenoid_wing"|"other"]|null,
      "age_bucket": "<50"|"50-65"|">=65"|null,
      "gender": "M"|"F"|null,
      "first_action": "surgery"|"radiation"|"wait_and_watch"|null,
      "any_action":   "surgery"|"radiation"|"wait_and_watch"|null,
      "not_first_action": "surgery"|"radiation"|"wait_and_watch"|null,
      "not_any_action":   "surgery"|"radiation"|"wait_and_watch"|null,
      "outcome_filter": "functional"|"impaired"|null,
      "had_active_treatment": true|false|null
  },
  "arms": [{"label": "...", "filter": {...positive AND negation atoms...}}, ...] | null,
  "stratifier": "grade"|"age"|"location"|"gender"|null,
  "time_window": {"from_action": "surgery"|"radiation"|"diagnosis"|null,
                  "to_action":   "surgery"|"radiation"|"diagnosis"|null,
                  "max_months":  number|null} | null,
  "pathways": [{"label": "...", "filter": {...}}, ...] | null,
  "adjusters": ["size_at_l1_cm"|"symptomatic_at_l1"|"age_years"|"location"|"grade", ...] | null,
  "parts": [<plan dict>, ...] | null,
  "primary_outcome": "functional_status"|"trajectory_distribution"|"time_to_event",
  "router_rationale": "1 sentence"
}

QTYPE RULES (apply in order):
1. COMPOUND: question joins two distinct asks (e.g., patterns AND outcomes).
2. COMPARATIVE-ADJUSTED: explicit "after adjusting for X, Y, and Z" with 2+ adjusters.
3. TEMPORAL-CONDITIONAL: cohort split by time window between two events.
4. PATHWAY-FUNNEL: 2+ named treatment pathways enumerated.
5. SUBGROUP-COMPARATIVE: how outcomes vary across all strata of one dimension.
6. TRAJECTORY: treatment sequences, escalation patterns.
7. COMPARATIVE: exactly two named groups contrasted on outcome.
8. DESCRIPTIVE-TEMPORAL: descriptive + median time-to-event.
9. DESCRIPTIVE: one group + outcome rate + profile.
10. FACTUAL: single proportion or count.

ATOM USAGE NOTES (important — these are common failure modes):

A. outcome_filter is the TOPIC vs FILTER distinction:
   - Set outcome_filter="functional" or "impaired" ONLY when the question
     restricts the cohort to that outcome (e.g., "among impaired patients...").
   - DO NOT set outcome_filter when the question asks how the outcome
     varies/differs/distributes — the outcome is then the dependent variable,
     not a filter.
   - Example: "How do functional outcomes vary across grades?" -> outcome_filter
     is NULL (not "functional"); the cohort is unrestricted; the question is
     about variation IN the outcome.

B. PATHWAY-FUNNEL with "alternatives":
   - Pathways must be MUTUALLY EXCLUSIVE. Patients are assigned to the FIRST
     matching pathway in the order you list them.
   - To express "alternatives" (= the complement of all named pathways),
     emit a pathway with an EMPTY filter ({}) — the executor treats it as the
     complement of all earlier pathways.
   - Example: surgery-then-radiation vs alternatives:
       pathways: [
         {"label": "Surgery -> Radiation",
          "filter": {"first_action": "surgery",
                     "l2_action_anywhere": "radiation"}},
         {"label": "Alternatives", "filter": {}}
       ]

C. SUBGROUP-COMPARATIVE arms:
   - If the question asks about per-stratum DESCRIPTION (e.g., "How do
     functional outcomes vary across WHO grades?"), OMIT arms entirely
     (arms = null). The executor will report per-stratum N + rate + CI +
     chi-square across strata. Do NOT set outcome_filter.
   - If the question asks "what profile distinguishes functional from
     impaired patients, by grade", omit arms but DO NOT set outcome_filter;
     the executor will compare functional vs impaired across strata.
   - If the question asks for a specific two-arm contrast within strata, set
     arms with explicit filters.

D. Negation atoms ("X alone vs X then Y"):
   - To express "first treatment = surgery WITHOUT later radiation" use
     {"first_action": "surgery", "not_l2_action_anywhere": "radiation"}.
   - To express "patient never received Y at any level" use
     {"not_any_action": "radiation"}.
   - To express "patient's first action was NOT X" use
     {"not_first_action": "wait_and_watch"}.

FILTER VOCABULARY: use exactly the atoms named above.
ADJUSTERS: size_at_l1_cm, symptomatic_at_l1, age_years, location, grade.

GUARDRAILS:
- NEVER invent a filter atom.
- NEVER emit numbers.
- NEVER comment on the answer.
- Output ONLY the JSON plan.
"""

_VALID_QTYPES = {"FACTUAL", "DESCRIPTIVE", "DESCRIPTIVE-TEMPORAL", "COMPARATIVE",
                 "SUBGROUP-COMPARATIVE", "TRAJECTORY", "TEMPORAL-CONDITIONAL",
                 "PATHWAY-FUNNEL", "COMPARATIVE-ADJUSTED", "COMPOUND"}
_VALID_FILTER_KEYS = {"grade", "location", "age_bucket", "gender",
                      "first_action", "any_action", "outcome_filter",
                      "had_active_treatment",
                      # negation atoms — used for "X alone vs X then Y" patterns
                      "not_first_action", "not_any_action",
                      "not_l2_action_anywhere",
                      # arm-specific extras
                      "l2_action_anywhere", "l2_action", "second_action",
                      "nccn_pattern", "escalation_class"}
_VALID_GRADES = {"grade_1", "grade_2", "grade_3"}
_VALID_LOCATIONS = {"convexity", "skull_base", "parasagittal",
                    "sphenoid_wing", "other"}
_VALID_AGE_BUCKETS = {"<50", "50-65", ">=65"}
_VALID_ACTIONS = {"surgery", "radiation", "wait_and_watch"}
_VALID_ADJUSTERS = {"size_at_l1_cm", "symptomatic_at_l1", "age_years",
                    "location", "grade"}


def verify_router_plan(plan):
    if not isinstance(plan, dict): return False, "not a dict"
    qt = plan.get("qtype")
    if qt not in _VALID_QTYPES: return False, f"qtype '{qt}' invalid"
    bf = plan.get("base_filter") or {}
    if not isinstance(bf, dict): return False, "base_filter not dict"
    for k in bf:
        if k not in _VALID_FILTER_KEYS: return False, f"unknown filter key '{k}'"
    g = bf.get("grade")
    if g and g not in _VALID_GRADES: return False, f"invalid grade '{g}'"
    loc = bf.get("location")
    if loc:
        if isinstance(loc, str): loc = [loc]
        for v in loc:
            if v not in _VALID_LOCATIONS: return False, f"invalid location '{v}'"
    if bf.get("age_bucket") and bf["age_bucket"] not in _VALID_AGE_BUCKETS:
        return False, "invalid age_bucket"
    for k in ("first_action", "any_action"):
        if bf.get(k) and bf[k] not in _VALID_ACTIONS:
            return False, f"invalid {k}"
    if qt in ("COMPARATIVE", "TEMPORAL-CONDITIONAL", "COMPARATIVE-ADJUSTED"):
        arms = plan.get("arms")
        if not (isinstance(arms, list) and len(arms) == 2):
            return False, f"{qt} requires 2 arms"
    if qt == "PATHWAY-FUNNEL":
        pw = plan.get("pathways")
        if not (isinstance(pw, list) and len(pw) >= 2):
            return False, "needs >=2 pathways"
    if qt == "SUBGROUP-COMPARATIVE":
        if not plan.get("stratifier"): return False, "needs stratifier"
    if qt == "TEMPORAL-CONDITIONAL":
        tw = plan.get("time_window") or {}
        if not (tw.get("max_months") and tw.get("from_action") and tw.get("to_action")):
            return False, "needs time_window"
    if qt == "COMPARATIVE-ADJUSTED":
        adj = plan.get("adjusters")
        if not (isinstance(adj, list) and len(adj) >= 2):
            return False, "needs >=2 adjusters"
        for a in adj:
            if a not in _VALID_ADJUSTERS: return False, f"invalid adjuster '{a}'"
    if qt == "COMPOUND":
        parts = plan.get("parts")
        if not (isinstance(parts, list) and len(parts) >= 2):
            return False, "needs >=2 parts"
        for i, part in enumerate(parts):
            ok, c = verify_router_plan(part)
            if not ok: return False, f"part {i}: {c}"
    return True, ""


def route_question(question, api_key, max_retries=2):
    last = None
    for attempt in range(max_retries + 1):
        plan = _llm_json(ROUTER_SYSTEM_PROMPT, question, api_key,
                        max_tokens=ROUTER_MAX_TOKENS, temperature=ROUTER_TEMPERATURE)
        if "_error" in plan:
            last = plan["_error"]; continue
        ok, c = verify_router_plan(plan)
        if ok: return {"plan": plan, "accepted": True,
                       "retries": attempt, "failure_reason": None}
        last = f"plan_verification_failed: {c}"
    return {"plan": None, "accepted": False,
            "retries": max_retries, "failure_reason": last}


# =====================================================================
# Synthesis prompts
# =====================================================================

INTERPRETATION_SYSTEM_PROMPT = """You are a clinical biostatistician writing
the INTERPRETATION paragraph of a TWO-ARM analysis answer.

You receive a LOCKED ANALYSIS BLOCK. Write ONE paragraph (3-5 sentences):
SENTENCE 1: Direction of imbalances on each feature with SMD > 0.10.
SENTENCE 2: Name the clinical pattern: "confounding by indication", "referral
bias", "selection effects", "appropriate treatment selection", "lead-time bias".
SENTENCE 3: Whether the outcome direction is consistent with the imbalance pattern.

FORBIDDEN causal language. EVERY NUMBER must come verbatim from the block.

Output JSON: {"interpretation": "..."}
"""


STRATIFIED_DESC_INTERPRETATION_SYSTEM_PROMPT = """You are a clinical
biostatistician writing the INTERPRETATION paragraph of a STRATIFIED
DESCRIPTIVE analysis. The question asks how a functional-outcome rate varies
across the strata of a single dimension (e.g., WHO grade, age band, location).
There are NO two arms and NO selection-effect / confounding-by-indication
narrative to construct — describe the gradient, not a treatment contrast.

You receive a LOCKED ANALYSIS BLOCK with per-stratum N + functional rate + CI
and a chi-square test across strata. Write ONE paragraph (3-5 sentences):

SENTENCE 1: Lead with the substantive finding. Name the direction and
magnitude of the gradient (e.g., "Functional rates fall sharply from X% in
the lowest-risk stratum to Y% in the highest-risk stratum"). Cite the two
extreme stratum rates verbatim.
SENTENCE 2: State whether the chi-square test rejects homogeneity (cite chi2,
df, p) and what that means in plain language ("the gradient is unlikely to
be chance" / "rates are not distinguishable").
SENTENCE 3: Name the stratum where precision is weakest (smallest N) and what
that limits.
OPTIONAL SENTENCE 4: Note whether the direction is clinically reasonable for
this dimension (e.g., higher WHO grade lower functional rate is biologically
expected; you may say "consistent with the known biology").

FORBIDDEN: causal language ("causes", "leads to"), confounding-by-indication
language, selection-effect language, baseline-imbalance language — there are
no two arms here so these frames do not apply.

EVERY NUMBER you cite MUST come verbatim from the LOCKED BLOCK.

Output JSON: {"interpretation": "..."}
"""

CAVEATS_SYSTEM_PROMPT = """You write CAVEATS for an analysis answer.

You receive the LOCKED BLOCK and a list of DETERMINISTIC CAVEATS already injected.
Add 1-3 ADDITIONAL caveats specific to the question.

Each caveat = {label (2-5 words), body (1-2 sentences citing exact numbers from
the block), anchor (the quantitative fact)}.

Numbers MUST come from the block. No causal language. No duplicates of the
deterministic list.

Output JSON: {"additional_caveats": [{"label","body","anchor"}, ...]}
"""

RESPONSIVITY_SYSTEM_PROMPT = """You are the FINAL EDITOR. You receive:
- the QUESTION,
- the ASSEMBLED ANSWER OBJECT (draft direct_answer + comparison_summary +
  adjusted_analysis + llm_caveats),
- the LOCKED DETERMINISTIC CAVEATS (cannot drop or modify).

Job:
1. Rewrite direct_answer so its FIRST SENTENCE LITERALLY ADDRESSES THE QUESTION.
   The rest carries headline numbers verbatim from comparison_summary (per-arm
   N, rate with CI, abs diff, Fisher's p, adjusted contrast if applicable).
   End with: "No causal claim is supported; this is an observational comparison
   at the association tier" (or "adjusted observational comparison, not
   identified causal effect" if COMPARATIVE-ADJUSTED).
2. Reorder llm_caveats by relevance; may drop irrelevant ones; may NOT drop or
   modify locked deterministic caveats. ALSO drop any llm_caveat whose label
   or substance duplicates a locked caveat.

Do NOT invent or recompute any number.

Output JSON: {"direct_answer": "...", "reordered_llm_caveats": [...]}
"""


STRATIFIED_DESC_RESPONSIVITY_SYSTEM_PROMPT = """You are the FINAL EDITOR for
a STRATIFIED DESCRIPTIVE analysis (variation of a rate across the strata of
a single dimension — there are NO two arms).

You receive:
- the QUESTION,
- the ASSEMBLED ANSWER OBJECT (draft direct_answer + stratified_descriptive
  rows + chi_square_across_strata + llm_caveats),
- the LOCKED DETERMINISTIC CAVEATS (cannot drop or modify).

Job:
1. Rewrite direct_answer so its FIRST SENTENCE LITERALLY ADDRESSES THE QUESTION
   with the SUBSTANTIVE FINDING — name the gradient direction and the
   highest/lowest rates. Example: "Functional outcomes drop sharply with
   higher WHO grade: 73.8% in grade 1, 38.6% in grade 2, 36.4% in grade 3."
   THEN cite the chi-square test result if available, in plain language
   ("the gradient is unlikely to be chance, chi² = 24.3, df = 2, p < 0.001"
   or "the rates are not distinguishable, chi² = 1.2, df = 2, p = 0.55").
   THEN at most one sentence on which stratum is least precise.
   End with: "No causal claim is supported; this is an observational
   comparison at the association tier."

   DO NOT just list the numbers — lead with the FINDING.

2. Reorder llm_caveats by relevance; may drop irrelevant ones; may NOT drop
   or modify locked deterministic caveats. DROP any llm_caveat whose label or
   substance duplicates a locked caveat (case-insensitive label match counts).

DO NOT invent or recompute any number. EVERY number must come from the
draft or from chi_square_across_strata.

Output JSON: {"direct_answer": "...", "reordered_llm_caveats": [...]}
"""


# =====================================================================
# Deterministic caveats
# =====================================================================

def build_deterministic_caveats(plan, stats, balance, subgroups, evalue,
                                 extra_rows=None):
    """Build the locked caveats.

    `stats` is the two-arm comparison summary (comp). When the block is
    PATHWAY-FUNNEL or TRAJECTORY, callers should pass the pair_comp here so
    the E-value and underpowered caveats still fire.

    `extra_rows` is a list of {label, N} dicts (pathway rows, trajectory rows,
    or stratum rows) used to inject "suppressed [group]" caveats when any has
    N<3 or N<15.
    """
    out = []
    qt = plan.get("qtype") if plan else None
    if balance:
        imb = [r for r in balance if r.get("imbalanced")]
        sub = [r for r in balance if r.get("substantial")]
        if imb:
            feats = ", ".join(r["feature"] for r in sub[:3]) or \
                    ", ".join(r["feature"] for r in imb[:3])
            out.append({
                "label": "Strong selection effects",
                "body": (f"The two arms differ at baseline on {len(imb)} measured "
                         f"features (SMD > 0.10); {feats} most strongly imbalanced. "
                         f"A propensity-matched or formal causal analysis would be "
                         f"required to estimate a treatment effect."),
                "anchor": f"{len(sub)} SMD>0.25, {len(imb)} SMD>0.10",
                "locked": True,
            })
    if evalue and evalue.get("evalue_point") is not None:
        ep = evalue["evalue_point"]
        if ep < 2.0:
            i = "an unmeasured confounder of only modest strength would suffice to overturn this observation"
        elif ep < 4.0:
            i = "an unmeasured confounder of moderate strength would be required to overturn this observation"
        else:
            i = "only a strong unmeasured confounder could overturn this observation; the contrast is relatively robust"
        out.append({
            "label": "Sensitivity to unmeasured confounding",
            "body": f"E-value at the point estimate is {ep}: {i}.",
            "anchor": f"E-value={ep}", "locked": True,
        })
    if stats and stats.get("n_a") and stats.get("n_b"):
        n_a, n_b = stats["n_a"], stats["n_b"]
        if min(n_a, n_b) < 50:
            base = (stats.get("rate_b_pct") or 50) / 100.0
            mde = compute_mde(n_a, n_b, baseline_rate=base)
            out.append({
                "label": "Underpowered for clinically meaningful differences",
                "body": (f"With n={n_a} vs n={n_b}, this analysis can reliably "
                         f"detect only differences of about {mde} percentage "
                         f"points or larger; smaller but clinically relevant "
                         f"differences would be missed."),
                "anchor": f"n={n_a} vs n={n_b}; MDE={mde} pp",
                "locked": True,
            })
    if subgroups:
        for sname, sblock in subgroups.items():
            supp = [r for r in (sblock.get("rows") or [])
                   if r.get("reliability") == "Suppressed"]
            if supp:
                names = ", ".join(r["stratum"] for r in supp[:3])
                out.append({
                    "label": f"Suppressed strata in {sblock.get('stratifier_display', sname)}",
                    "body": (f"Counts in {names} are below the suppression threshold "
                             f"(N<3 per arm); per-stratum results are not interpretable."),
                    "anchor": f"{len(supp)} suppressed strata", "locked": True,
                })
                break
    if qt == "COMPARATIVE-ADJUSTED":
        adj = plan.get("adjusters") or []
        out.append({
            "label": "Adjusted observational comparison, not identified causal",
            "body": (f"Inverse-probability weighting on {', '.join(adj)} removes "
                     f"imbalance on these covariates but does not perform "
                     f"sensitivity analysis under unmeasured confounding; the "
                     f"adjusted contrast is short of an identified causal effect."),
            "anchor": f"adjusters: {', '.join(adj)}", "locked": True,
        })
    # Suppressed/underpowered groups in non-two-arm blocks (pathways,
    # trajectories, strata)
    if extra_rows:
        small = [r for r in extra_rows if (r.get("N") or 0) < 15]
        if small:
            kind = "groups"
            if qt == "PATHWAY-FUNNEL": kind = "pathways"
            elif qt == "TRAJECTORY": kind = "trajectories"
            elif qt == "SUBGROUP-COMPARATIVE": kind = "strata"
            names = ", ".join(f"{r.get('label')} (N={r.get('N')})"
                             for r in small[:3])
            out.append({
                "label": f"Underpowered {kind}",
                "body": (f"{len(small)} {kind} have N < 15: {names}. "
                         f"Per-{kind[:-1]} estimates are exploratory; only "
                         f"large effects would be detectable."),
                "anchor": f"{len(small)} {kind} with N<15", "locked": True,
            })
    return out


# =====================================================================
# Verifiers
# =====================================================================

_NUMBER_RE = re.compile(r"(?<![A-Za-z])([0-9]+(?:\.[0-9]+)?)(?![A-Za-z])")

def _extract_numbers(text):
    return [float(m.group(1)) for m in _NUMBER_RE.finditer(text or "")]


def verify_numeric_grounding(text, stats_block, tolerances=None):
    tol = tolerances or VERIFIER_TOLERANCES
    locked = set(_extract_numbers(stats_block or ""))
    nums = _extract_numbers(text)
    missing = []
    for n in nums:
        t = max(tol["risk_ratio"], tol["evalue"]) if n < 5 else tol["percentage_pp"]
        if any(abs(n-L) <= t for L in locked): continue
        if int(n) == n and any(int(n) == int(L) for L in locked if int(L) == L):
            continue
        derived = False
        for L1 in locked:
            for L2 in locked:
                for op in (L1-L2, L1+L2):
                    if abs(n-op) <= t: derived = True; break
                if derived: break
            if derived: break
        if not derived: missing.append(n)
    return {"ok": len(missing) == 0, "missing_numbers": missing,
            "total_numbers": len(nums)}


_ENTITY_PATTERNS = [
    "grade 1", "grade 2", "grade 3", "grade_1", "grade_2", "grade_3",
    "WHO", "tumour grade", "tumor grade", "tumour", "tumor",
    "convexity", "skull-base", "skull_base", "parasagittal", "sphenoid_wing",
    "surgery", "radiation", "wait-and-watch", "wait_and_watch",
    "watchful waiting", "GTR", "STR", "biopsy",
    "first treatment", "second treatment",
    "functional outcome", "functional outcomes", "functional rate",
    "vary", "varies", "across grades", "across age",
    "adjuvant", "upfront", "escalating", "de-escalating", "NCCN",
    "symptomatic", "incidental", "alone",
]


def entity_recall_check(question, direct_answer):
    q = (question or "").lower()
    a = (direct_answer or "").lower()
    in_q = [e for e in _ENTITY_PATTERNS if e.lower() in q]
    for m in re.finditer(r"(\d+)\s*(months?|years?)", q):
        in_q.append(m.group(0))
    if not in_q: return {"ok": True, "found": [], "missing": []}
    found = [e for e in in_q if e.lower() in a]
    missing = [e for e in in_q if e.lower() not in a]
    return {"ok": len(missing) == 0, "found": found, "missing": missing}


# =====================================================================
# Locked-block text renderer
# =====================================================================

def render_locked_block(plan, stats_summary, outcomes_rows, cohort_funnel,
                        baseline, subgroups, evalue, mde=None,
                        followup=None, modality=None, adjusted=None,
                        question_text="",
                        stratified_descriptive=None):
    lines = []
    if question_text: lines += [f"QUESTION: {question_text}", ""]
    if plan: lines += [f"QTYPE: {plan.get('qtype')}", ""]
    if cohort_funnel:
        lines.append("COHORT CONSTRUCTION:")
        for r in cohort_funnel.get("rows", []):
            d = r.get("delta_from_prev")
            ds = f" (delta {d:+d})" if isinstance(d, int) else ""
            lines.append(f"  - {r['step_description']}: N={r['N']}{ds}")
        lines.append("")
    if outcomes_rows:
        lines.append("OUTCOMES TABLE:")
        for r in outcomes_rows:
            lo, hi = r.get("ci_pct", (None, None))
            lines.append(f"  - {r['arm']}: N={r['N']}, functional={r['n_functional']}, "
                        f"rate={r['rate_pct']}% [95% CI: {lo}-{hi}%]")
        lines.append("")
    if stats_summary:
        s = stats_summary
        rr_ci = s.get("rr_ci") or (None, None)
        d_ci = s.get("abs_diff_ci_pp") or (None, None)
        lines.append("COMPARISON SUMMARY:")
        lines.append(f"  - Absolute difference: {s.get('abs_diff_pp')} pp "
                    f"[95% CI: {d_ci[0]} to {d_ci[1]} pp]")
        lines.append(f"  - Risk ratio: {s.get('rr')} [95% CI: {rr_ci[0]}-{rr_ci[1]}]")
        lines.append(f"  - Fisher's exact p: {s.get('fishers_exact_p')}")
        if evalue:
            lines.append(f"  - E-value (point): {evalue.get('evalue_point')}")
            lines.append(f"  - E-value (CI bound): {evalue.get('evalue_ci_bound')}")
        lines.append("")
    if adjusted:
        lines.append("ADJUSTED ANALYSIS (multi-covariate IPW):")
        lines.append(f"  - adjusters: {adjusted.get('adjusters')}")
        lines.append(f"  - unadjusted abs diff: {adjusted.get('unadjusted_abs_diff_pp')} pp")
        lines.append(f"  - adjusted abs diff: {adjusted.get('adjusted_abs_diff_pp')} pp")
        lines.append(f"  - adjusted RR: {adjusted.get('adjusted_rr')} "
                    f"[95% CI: {adjusted.get('adjusted_rr_ci')}]")
        lines.append(f"  - gap: {adjusted.get('gap_pp')} pp")
        lines.append("")
    if baseline:
        lines.append("BASELINE BALANCE (SMD > 0.10 flagged):")
        for r in baseline:
            keys = [k for k in r if k.startswith("arm_")]
            a = r.get(keys[0], "-") if keys else "-"
            b = r.get(keys[1], "-") if len(keys) > 1 else "-"
            flag = " [IMBALANCED]" if r.get("imbalanced") else ""
            lines.append(f"  - {r['feature']}: A={a}, B={b}, SMD={r['smd']}{flag}")
        lines.append("")
    if subgroups:
        for sname, sblock in subgroups.items():
            lines.append(f"STRATIFIED BY {sblock.get('stratifier_display', sname).upper()}:")
            for r in sblock.get("rows", []):
                keys = [k for k in r if k.startswith("arm_")]
                a = r.get(keys[0], "-") if keys else "-"
                b = r.get(keys[1], "-") if len(keys) > 1 else "-"
                lines.append(f"  - {r['stratum']}: A={a}; B={b}; "
                            f"diff={r.get('difference', '-')}; "
                            f"reliability={r.get('reliability', '-')}")
            lines.append("")
    if stratified_descriptive:
        sd = stratified_descriptive
        strat = (sd.get("stratifier") or "stratum").upper()
        lines.append(f"FUNCTIONAL OUTCOMES BY {strat}:")
        for r in sd.get("rows", []) or []:
            lo, hi = r.get("ci_pct", (None, None))
            lines.append(f"  - {r['stratum']}: N={r['N']}, "
                         f"functional={r.get('n_functional')}, "
                         f"rate={r.get('rate_pct')}% "
                         f"[95% CI: {lo}-{hi}%], "
                         f"reliability={r.get('reliability','-')}")
        chi = sd.get("chi_square_across_strata") or {}
        if chi.get("p_value") is not None:
            lines.append(f"  - chi-square across strata: chi2={chi.get('chi2')}, "
                         f"df={chi.get('dof')}, p={chi.get('p_value')} "
                         f"({chi.get('strata_used')} strata)")
        lines.append("")
    if mde is not None:
        lines += [f"POWER: MDE at alpha=0.05, power=0.80 = {mde} pp", ""]
    if followup:
        lines += [f"FOLLOW-UP: months at last event range "
                 f"{followup['min_months']}-{followup['max_months']} "
                 f"(median {followup['median_months']})", ""]
    if modality:
        ms = "; ".join(f"{k}: {v}" for k, v in modality.items())
        lines += [f"RADIATION MODALITY BREAKDOWN: {ms}", ""]
    return "\n".join(lines)


# =====================================================================
# Patient/cohort helpers
# =====================================================================

def _p_strat(p, key): return (p.get("stratification") or {}).get(key)
def _p_level_action(p, n): return (p.get("level_info") or {}).get(n, {}).get("action")

def _p_action_seq(p):
    seq = p.get("action_sequence")
    if seq: return list(seq)
    li = p.get("level_info") or {}
    return [li[lv].get("action", "") for lv in sorted(li)]

def _p_has_any_action(p, a): return a in _p_action_seq(p)

def _p_match_nccn(seq):
    if "surgery" not in seq: return False
    i = seq.index("surgery")
    return "radiation" in seq[i+1:]

def _p_classify_escalation(seq):
    OBS = {"wait_and_watch"}; ACT = {"surgery", "radiation"}
    if not seq: return "no_interventions"
    has_obs = any(a in OBS for a in seq)
    has_act = any(a in ACT for a in seq)
    if not has_act: return "stable_observation"
    if not has_obs and len(set(seq)) == 1: return "stable_treatment"
    if seq[0] in OBS and has_act: return "escalating"
    if seq[0] == "surgery" and "radiation" in seq[1:]: return "escalating"
    if seq[0] in ACT and len(seq) > 1 and seq[-1] in OBS: return "de-escalating"
    return "complex"

def _p_months_at_first_action(p, a):
    seq = _p_action_seq(p)
    if a not in seq: return None
    lv = seq.index(a) + 1
    li = (p.get("level_info") or {}).get(lv) or {}
    v = li.get("months_since_diagnosis")
    if v is None: return None
    try: return float(v)
    except Exception: return None


def _matches_filter(p, atoms):
    if not atoms: return True
    g = atoms.get("grade")
    if g and _p_strat(p, "grade") != g: return False
    loc = atoms.get("location")
    if loc:
        if isinstance(loc, str): loc = [loc]
        if _p_strat(p, "location") not in loc: return False
    ab = atoms.get("age_bucket")
    if ab and _p_strat(p, "age") != ab: return False
    gen = atoms.get("gender")
    if gen and _p_strat(p, "gender") != gen: return False
    fa = atoms.get("first_action") or atoms.get("l1_action")
    if fa and _p_level_action(p, 1) != fa: return False
    # negation: not_first_action
    nfa = atoms.get("not_first_action")
    if nfa and _p_level_action(p, 1) == nfa: return False
    aa = atoms.get("any_action")
    if aa and not _p_has_any_action(p, aa): return False
    # negation: not_any_action (patient must NOT have action a at any level)
    naa = atoms.get("not_any_action")
    if naa and _p_has_any_action(p, naa): return False
    of = atoms.get("outcome_filter")
    if of and p.get("functional_status") != of: return False
    hat = atoms.get("had_active_treatment")
    if hat is True and not (_p_has_any_action(p, "surgery") or _p_has_any_action(p, "radiation")):
        return False
    if hat is False and (_p_has_any_action(p, "surgery") or _p_has_any_action(p, "radiation")):
        return False
    l2 = atoms.get("l2_action") or atoms.get("second_action")
    if l2 and _p_level_action(p, 2) != l2: return False
    l2a = atoms.get("l2_action_anywhere")
    if l2a:
        seq = _p_action_seq(p)
        if l2a not in seq[1:]: return False
    # negation: not_l2_action_anywhere ("X alone" — no Y after the first action)
    nl2a = atoms.get("not_l2_action_anywhere")
    if nl2a:
        seq = _p_action_seq(p)
        if nl2a in seq[1:]: return False
    nccn = atoms.get("nccn_pattern")
    if nccn is True and not _p_match_nccn(_p_action_seq(p)): return False
    if nccn is False and _p_match_nccn(_p_action_seq(p)): return False
    ec = atoms.get("escalation_class")
    if ec and _p_classify_escalation(_p_action_seq(p)) != ec: return False
    return True


def _apply_base(plan, cohort):
    bf = plan.get("base_filter") or {}
    return [p for p in cohort if _matches_filter(p, bf)]


def _apply_arm(subset, arm_spec):
    f = (arm_spec or {}).get("filter") or {}
    return [p for p in subset if _matches_filter(p, f)]


# =====================================================================
# Stratified table builder
# =====================================================================

_STRATIFIER_DISPLAY = {"grade": "WHO Grade", "age": "Age stratum",
                       "location": "Location", "gender": "Gender"}


def _arm_summary(records, arm_label):
    n = len(records)
    k = sum(1 for r in records if _outcome_of(r) == "functional")
    if n == 0: return "n=0"
    rate = (k/n)*100
    lo, hi = clopper_pearson(k, n)
    return f"{k}/{n} ({rate:.1f}% [95% CI: {lo*100:.1f}-{hi*100:.1f}%])"


def stratified_table(group_a, group_b, stratifier, arm_a_label="A", arm_b_label="B"):
    def _key(p): return _p_strat(p, stratifier)
    strata = sorted({_key(p) for p in list(group_a) + list(group_b)
                    if _key(p) is not None}, key=lambda x: str(x))
    aa, bb = f"arm_{arm_a_label}", f"arm_{arm_b_label}"
    rows = []
    for s in strata:
        a_s = [p for p in group_a if _key(p) == s]
        b_s = [p for p in group_b if _key(p) == s]
        rel = assign_reliability(len(a_s), len(b_s))
        if rel["suppressed"]:
            rows.append({"stratum": str(s),
                        aa: f"n={len(a_s)} (suppressed)",
                        bb: f"n={len(b_s)} (suppressed)",
                        "difference": "-", "reliability": rel["tag"]})
            continue
        _, comp = fisher_and_effect(a_s, b_s, arm_a_label=arm_a_label,
                                    arm_b_label=arm_b_label)
        rows.append({
            "stratum": str(s),
            aa: _arm_summary(a_s, arm_a_label),
            bb: _arm_summary(b_s, arm_b_label),
            "difference": (f"{comp['abs_diff_pp']:+.1f} pp"
                          if comp["abs_diff_pp"] is not None else "-"),
            "reliability": rel["tag"],
        })
    return {"stratifier_key": stratifier,
            "stratifier_display": _STRATIFIER_DISPLAY.get(stratifier, stratifier),
            "gloss": GLOSSES["subgroup_detail"],
            "reliability_legend": RELIABILITY_LEGEND, "rows": rows}


def build_subgroups(group_a, group_b, label_a, label_b):
    return {s: stratified_table(group_a, group_b, s, label_a, label_b)
            for s in STRATIFIERS}


def stratum_counts_for_cmh(group_a, group_b, stratifier):
    def _key(p): return _p_strat(p, stratifier)
    strata = sorted({_key(p) for p in list(group_a) + list(group_b)
                    if _key(p) is not None}, key=lambda x: str(x))
    out = []
    for s in strata:
        a_s = [p for p in group_a if _key(p) == s]
        b_s = [p for p in group_b if _key(p) == s]
        ae = sum(1 for r in a_s if _outcome_of(r) == "functional")
        be = sum(1 for r in b_s if _outcome_of(r) == "functional")
        out.append({"stratum": str(s), "a_event": ae, "a_n": len(a_s),
                    "b_event": be, "b_n": len(b_s)})
    return out


# =====================================================================
# Multi-covariate IPW
# =====================================================================

def _design_row(p, adjusters):
    row = []
    for a in adjusters:
        v = extract_feature(p, a)
        if v is None: return None
        if a == "location":
            order = ["convexity", "skull_base", "parasagittal", "sphenoid_wing", "other"]
            try: row.append(order.index(v))
            except ValueError: row.append(len(order))
        elif a == "grade":
            row.append({"grade_1": 1, "grade_2": 2, "grade_3": 3}.get(v, 0))
        else:
            try: row.append(float(v))
            except Exception: return None
    return row


def multivariate_ipw(group_a, group_b, adjusters, label_a="A", label_b="B"):
    method = None
    weights_a, weights_b = [], []
    if _HAS_SKLEARN and len(group_a) >= 5 and len(group_b) >= 5:
        try:
            X, y = [], []
            ka, kb = [], []
            for p in group_a:
                r = _design_row(p, adjusters)
                if r is not None: X.append(r); y.append(1); ka.append(p)
            for p in group_b:
                r = _design_row(p, adjusters)
                if r is not None: X.append(r); y.append(0); kb.append(p)
            if len(set(y)) == 2 and len(X) >= 10:
                m = _SkLR(max_iter=200, solver="lbfgs")
                m.fit(X, y)
                ps = m.predict_proba(X)[:, 1]
                n_a = len(ka)
                psc = [min(max(p_, 0.05), 0.95) for p_ in ps]
                w = [1.0/p_ if y[i] == 1 else 1.0/(1-p_) for i, p_ in enumerate(psc)]
                weights_a, weights_b = w[:n_a], w[n_a:]
                group_a, group_b = ka, kb
                method = "sklearn_logistic"
        except Exception as e:
            method = f"sklearn_failed: {e}"
    if method is None or (method or "").startswith("sklearn_failed"):
        first = adjusters[0]
        def _bin(p):
            v = extract_feature(p, first)
            if v is None: return None
            if first == "size_at_l1_cm":
                return "small" if v < 2 else "medium" if v < 4 else "large"
            if first == "age_years":
                return "<50" if v < 50 else "50-65" if v < 65 else ">=65"
            return v
        levels = _defaultdict(lambda: {"a": [], "b": []})
        for p in group_a:
            b = _bin(p)
            if b is not None: levels[b]["a"].append(p)
        for p in group_b:
            b = _bin(p)
            if b is not None: levels[b]["b"].append(p)
        ka, kb = [], []
        for lv, arms in levels.items():
            n = len(arms["a"]) + len(arms["b"])
            if n == 0: continue
            p_a = len(arms["a"]) / n
            p_b = 1 - p_a
            for r in arms["a"]:
                weights_a.append(1.0/max(p_a, 0.05)); ka.append(r)
            for r in arms["b"]:
                weights_b.append(1.0/max(p_b, 0.05)); kb.append(r)
        group_a, group_b = ka, kb
        method = method or "stratified_fallback"
    def _wr(recs, ws):
        if not recs: return None
        num = sum(w for r, w in zip(recs, ws) if _outcome_of(r) == "functional")
        den = sum(ws)
        return num/den if den > 0 else None
    ra = _wr(group_a, weights_a)
    rb = _wr(group_b, weights_b)
    diff = ((ra-rb)*100 if ra is not None and rb is not None else None)
    rr = (ra/rb) if (ra is not None and rb and rb > 0) else None
    rr_ci = bootstrap_ratio_ci(group_a, group_b, weights_a, weights_b, B=500, seed=0)
    return {
        "method": method, "adjusters": adjusters,
        "adjusted_rate_a_pct": round(ra*100, 1) if ra else None,
        "adjusted_rate_b_pct": round(rb*100, 1) if rb else None,
        "adjusted_abs_diff_pp": round(diff, 1) if diff is not None else None,
        "adjusted_rr": round(rr, 2) if rr else None,
        "adjusted_rr_ci": rr_ci,
        "n_a_after_design": len(group_a), "n_b_after_design": len(group_b),
    }


# =====================================================================
# Per-qtype block builders
# =====================================================================

def _funnel_from_plan(plan, cohort, base_subset):
    funnel = CohortFunnel("Total cohort", total_n=len(cohort))
    bf = plan.get("base_filter") or {}
    if bf.get("grade"):
        funnel.record(f"WHO {bf['grade']}", len(base_subset))
    elif bf.get("location"):
        loc = bf["location"]
        ls = loc if isinstance(loc, str) else ", ".join(loc)
        funnel.record(f"Location: {ls}", len(base_subset))
    else:
        funnel.record("Base filter applied", len(base_subset))
    return funnel


def _build_two_arm(plan, cohort):
    base = _apply_base(plan, cohort)
    arms = plan.get("arms") or []
    a_spec, b_spec = arms[0], arms[1]
    la = a_spec.get("label") or "Arm A"
    lb = b_spec.get("label") or "Arm B"
    funnel = _funnel_from_plan(plan, cohort, base)
    ga = _apply_arm(base, a_spec); funnel.record(la, len(ga))
    gb = _apply_arm(base, b_spec); funnel.record(lb, len(gb))
    outcomes, comp = fisher_and_effect(ga, gb, arm_a_label=la, arm_b_label=lb)
    ev = compute_evalue(comp["rr"],
                       (comp.get("rr_ci") or (None, None))[0],
                       (comp.get("rr_ci") or (None, None))[1])
    comp.update(ev)
    balance = compute_baseline_balance(ga, gb, la, lb)
    subgroups = build_subgroups(ga, gb, la, lb)
    cmh = cochran_mantel_haenszel(stratum_counts_for_cmh(ga, gb, "grade"))
    subgroups["grade"]["cochran_mantel_haenszel"] = cmh
    mde = compute_mde(comp["n_a"], comp["n_b"],
                     baseline_rate=(comp.get("rate_b_pct") or 50) / 100)
    followup = compute_followup_range(ga + gb)
    modality = compute_modality_breakdown(ga + gb)
    rel = assign_reliability(comp["n_a"], comp["n_b"])
    return {"label_a": la, "label_b": lb, "group_a": ga, "group_b": gb,
            "funnel": funnel, "outcomes_rows": outcomes, "comp": comp,
            "balance": balance, "subgroups": subgroups,
            "mde": mde, "followup": followup, "modality": modality,
            "reliability": rel}


def build_block_factual(plan, cohort):
    base = _apply_base(plan, cohort)
    return {"qtype_block": "FACTUAL",
            "funnel": _funnel_from_plan(plan, cohort, base),
            "base": base, "value": len(base),
            "label": "Patients matching the base filter"}


def build_block_descriptive(plan, cohort):
    base = _apply_base(plan, cohort)
    funnel = _funnel_from_plan(plan, cohort, base)
    n = len(base)
    n_f = sum(1 for p in base if _outcome_of(p) == "functional")
    rate = (n_f/n*100) if n else None
    ci = clopper_pearson(n_f, n) if n else (0, 0)
    profile = []
    for display, key, ftype in BASELINE_FEATURES:
        values = [extract_feature(p, key) for p in base]
        if ftype == "continuous": s = _continuous_summary(values)
        elif ftype == "binary": s = _binary_summary(values)
        elif ftype == "binary_mf":
            vb = [1 if v == "F" else (0 if v == "M" else None) for v in values]
            s = f"F: {sum(1 for v in vb if v == 1)}; M: {sum(1 for v in vb if v == 0)}"
        else: s = _categorical_summary(values)
        profile.append({"feature": display, "value": s})
    return {"qtype_block": "DESCRIPTIVE", "funnel": funnel, "base": base,
            "n": n, "n_functional": n_f,
            "rate_pct": round(rate, 1) if rate is not None else None,
            "ci_pct": (round(ci[0]*100, 1), round(ci[1]*100, 1)),
            "profile": profile}


def build_block_descriptive_temporal(plan, cohort):
    desc = build_block_descriptive(plan, cohort)
    tw = plan.get("time_window") or {}
    target = tw.get("to_action") or "surgery"
    times = []
    for p in desc["base"]:
        t = _p_months_at_first_action(p, target)
        if t is not None: times.append(t)
    if times:
        med = _stats_std.median(times)
        s = sorted(times)
        q1 = s[max(0, int(len(times)*0.25)-1)]
        q3 = s[min(len(times)-1, int(len(times)*0.75))]
        desc["time_to_event"] = {"median_months": round(med, 1),
                                "iqr_months": (round(q1, 1), round(q3, 1)),
                                "n_with_event": len(times)}
    else:
        desc["time_to_event"] = {"median_months": None,
                                "iqr_months": (None, None), "n_with_event": 0}
    desc["target_event"] = target
    desc["qtype_block"] = "DESCRIPTIVE-TEMPORAL"
    return desc


def build_block_comparative(plan, cohort):
    b = _build_two_arm(plan, cohort); b["qtype_block"] = "COMPARATIVE"; return b


def build_block_temporal_conditional(plan, cohort):
    b = _build_two_arm(plan, cohort)
    b["qtype_block"] = "TEMPORAL-CONDITIONAL"
    b["time_window"] = plan.get("time_window")
    return b


def build_block_pathway_funnel(plan, cohort):
    """PATHWAY-FUNNEL with mutual exclusion.

    Patients are assigned to the FIRST pathway whose filter they match.
    A pathway with an empty filter is treated as "complement of all earlier
    pathways" — i.e., it captures every base patient not yet claimed.
    If no complement pathway is supplied and unclaimed patients remain, an
    implicit "Other trajectories" pathway is appended automatically.
    """
    base = _apply_base(plan, cohort)
    funnel = _funnel_from_plan(plan, cohort, base)
    pathways = plan.get("pathways") or []

    # Assign each base patient to the first matching pathway (mutual exclusion)
    assigned: Dict[int, list] = {i: [] for i in range(len(pathways))}
    unclaimed = []
    complement_idx = None  # index of the first pathway with an empty filter
    for i, pw in enumerate(pathways):
        f = (pw or {}).get("filter") or {}
        if not f and complement_idx is None:
            complement_idx = i
    for p in base:
        placed = False
        for i, pw in enumerate(pathways):
            f = (pw or {}).get("filter") or {}
            if not f:
                # complement pathway — never matches positively; falls through
                continue
            if _matches_filter(p, f):
                assigned[i].append(p); placed = True; break
        if not placed:
            unclaimed.append(p)
    if complement_idx is not None:
        assigned[complement_idx] = unclaimed
    else:
        # auto-append "Other trajectories" if there are unclaimed patients
        if unclaimed:
            pathways = pathways + [{"label": "Other trajectories", "filter": {}}]
            assigned[len(pathways) - 1] = unclaimed

    rows = []; pgroups = []
    for i, pw in enumerate(pathways):
        g = assigned.get(i, [])
        n = len(g)
        n_f = sum(1 for p in g if _outcome_of(p) == "functional")
        rate = (n_f/n*100) if n else None
        ci = clopper_pearson(n_f, n) if n else (0, 0)
        prev = (n/len(base)*100) if base else 0
        rows.append({"pathway": pw.get("label", "?"), "N": n,
                    "prevalence_pct": round(prev, 1), "n_functional": n_f,
                    "rate_pct": round(rate, 1) if rate is not None else None,
                    "ci_pct": (round(ci[0]*100, 1), round(ci[1]*100, 1))})
        pgroups.append((pw.get("label"), g))
        funnel.record(f"Pathway: {pw.get('label')}", n)

    # Pair contrast only when BOTH top two pathways have >=3 patients
    pair = None
    if len(pgroups) >= 2 and len(pgroups[0][1]) >= 3 and len(pgroups[1][1]) >= 3:
        _, pair = fisher_and_effect(pgroups[0][1], pgroups[1][1],
                                    arm_a_label=pgroups[0][0],
                                    arm_b_label=pgroups[1][0])
        ev = compute_evalue(pair["rr"],
                           (pair.get("rr_ci") or (None, None))[0],
                           (pair.get("rr_ci") or (None, None))[1])
        pair.update(ev)

    # Reliability tag from min pathway N; suppressed flag set if any pathway < 3
    pathway_ns = [len(g) for _, g in pgroups]
    min_n = min(pathway_ns) if pathway_ns else 0
    if min_n < 3:
        reliability = {"tag": "Suppressed (sparse pathway)", "suppressed": True}
    elif min_n < 15:
        reliability = {"tag": "Underpowered", "suppressed": False}
    elif min_n < 50:
        reliability = {"tag": "Limited", "suppressed": False}
    else:
        reliability = {"tag": "Adequate", "suppressed": False}

    return {"qtype_block": "PATHWAY-FUNNEL", "funnel": funnel, "base": base,
            "rows": rows, "pair_comp": pair,
            "reliability": reliability,
            "pathway_groups": pgroups,
            "min_pathway_n": min_n}


def build_block_subgroup_comparative(plan, cohort):
    """SUBGROUP-COMPARATIVE with three branches:

    (1) arms supplied -> per-stratum two-arm contrast across strata (Q8-style).
    (2) no arms + outcome_filter supplied -> functional-vs-impaired contrast
        within strata (legacy fallback).
    (3) no arms + no outcome_filter -> STRATIFIED DESCRIPTIVE: per-stratum N
        + functional rate + Clopper-Pearson CI + reliability tag + a
        chi-square test for variation across strata. This is the
        "how do outcomes vary across grade?" case.
    """
    base = _apply_base(plan, cohort)
    funnel = _funnel_from_plan(plan, cohort, base)
    stratifier = plan.get("stratifier") or "grade"
    arms = plan.get("arms")
    bf = plan.get("base_filter") or {}
    has_outcome_filter = bool(bf.get("outcome_filter"))

    # Branch 3: stratified-descriptive
    if not arms and not has_outcome_filter:
        return _build_stratified_descriptive(plan, cohort, base, funnel, stratifier)

    # Branches 1 and 2: two-arm contrast
    if not arms:
        ga = [p for p in base if _outcome_of(p) == "functional"]
        gb = [p for p in base if _outcome_of(p) == "impaired"]
        la, lb = "Functional", "Impaired"
        funnel.record("Functional", len(ga)); funnel.record("Impaired", len(gb))
    else:
        ga = _apply_arm(base, arms[0]); gb = _apply_arm(base, arms[1])
        la = arms[0].get("label", "A"); lb = arms[1].get("label", "B")
        funnel.record(la, len(ga)); funnel.record(lb, len(gb))
    table = stratified_table(ga, gb, stratifier, la, lb)
    cmh = cochran_mantel_haenszel(stratum_counts_for_cmh(ga, gb, stratifier))
    table["cochran_mantel_haenszel"] = cmh
    outcomes, comp = fisher_and_effect(ga, gb, arm_a_label=la, arm_b_label=lb)
    ev = compute_evalue(comp["rr"],
                       (comp.get("rr_ci") or (None, None))[0],
                       (comp.get("rr_ci") or (None, None))[1])
    comp.update(ev)
    balance = compute_baseline_balance(ga, gb, la, lb)
    rel = assign_reliability(comp["n_a"], comp["n_b"])
    return {"qtype_block": "SUBGROUP-COMPARATIVE", "funnel": funnel,
            "stratifier": stratifier, "label_a": la, "label_b": lb,
            "group_a": ga, "group_b": gb,
            "outcomes_rows": outcomes, "comp": comp,
            "stratified": table, "balance": balance, "reliability": rel}


def _build_stratified_descriptive(plan, cohort, base, funnel, stratifier):
    """Per-stratum N + functional rate + CI + reliability + chi-square."""
    def _key(p): return _p_strat(p, stratifier)
    strata = sorted({_key(p) for p in base if _key(p) is not None},
                    key=lambda x: str(x))
    rows = []
    contingency = []  # for chi-square: [[functional, impaired], ...] per stratum
    min_n = float("inf")
    for s in strata:
        sub = [p for p in base if _key(p) == s]
        n = len(sub)
        n_f = sum(1 for p in sub if _outcome_of(p) == "functional")
        n_i = sum(1 for p in sub if _outcome_of(p) == "impaired")
        rate = (n_f / n * 100) if n else None
        ci = clopper_pearson(n_f, n) if n else (0, 0)
        rel = assign_reliability(n, n)  # symmetric — one cohort per stratum
        rows.append({"stratum": str(s), "N": n,
                    "n_functional": n_f, "n_impaired": n_i,
                    "rate_pct": round(rate, 1) if rate is not None else None,
                    "ci_pct": (round(ci[0]*100, 1), round(ci[1]*100, 1)),
                    "reliability": rel["tag"]})
        # NOTE (v4.1): do NOT add per-stratum rows to the cohort funnel.
        # The funnel should only show the filtering progression to the
        # analysed cohort; per-stratum N belongs in the descriptive table.
        if n_f + n_i > 0:
            contingency.append([n_f, n_i])
            min_n = min(min_n, n_f + n_i)

    # Chi-square across strata
    chi_block = {"chi2": None, "p_value": None, "dof": None, "strata_used": 0}
    if len(contingency) >= 2:
        try:
            chi2, p, dof, _ = _scipy_stats.chi2_contingency(contingency)
            chi_block = {"chi2": round(float(chi2), 3),
                        "p_value": round(float(p), 4),
                        "dof": int(dof),
                        "strata_used": len(contingency)}
        except Exception:
            pass

    overall_rel = (assign_reliability(int(min_n), int(min_n))
                  if min_n != float("inf") else {"tag": "Suppressed", "suppressed": True})
    return {
        "qtype_block": "SUBGROUP-COMPARATIVE",
        "_subgroup_mode": "stratified_descriptive",
        "funnel": funnel, "stratifier": stratifier,
        "stratified_descriptive_rows": rows,
        "chi_square_across_strata": chi_block,
        "reliability": overall_rel,
        "n_total": sum(r["N"] for r in rows),
    }


def build_block_trajectory(plan, cohort):
    base = _apply_base(plan, cohort)
    funnel = _funnel_from_plan(plan, cohort, base)
    seqs = [tuple(_p_action_seq(p)) for p in base]
    n_total = sum(1 for s in seqs if s)
    counts = _Counter(seqs)
    rows = []
    for traj, n in counts.most_common(8):
        if not traj: continue
        subset = [p for p, s in zip(base, seqs) if s == traj]
        n_f = sum(1 for p in subset if _outcome_of(p) == "functional")
        rate = (n_f/n*100) if n else None
        ci = clopper_pearson(n_f, n) if n else (0, 0)
        rows.append({"trajectory": "->".join(traj), "N": n,
                    "percent_of_cohort": round((n/n_total*100) if n_total else 0, 1),
                    "n_functional": n_f,
                    "rate_pct": round(rate, 1) if rate is not None else None,
                    "ci_pct": (round(ci[0]*100, 1), round(ci[1]*100, 1))})

    # Pairwise Fisher between top two trajectories (if both >=3)
    pair = None
    if len(rows) >= 2 and rows[0]["N"] >= 3 and rows[1]["N"] >= 3:
        t1 = tuple(rows[0]["trajectory"].split("->"))
        t2 = tuple(rows[1]["trajectory"].split("->"))
        sub1 = [p for p, s in zip(base, seqs) if s == t1]
        sub2 = [p for p, s in zip(base, seqs) if s == t2]
        _, pair = fisher_and_effect(sub1, sub2,
                                    arm_a_label=rows[0]["trajectory"],
                                    arm_b_label=rows[1]["trajectory"])
        ev = compute_evalue(pair["rr"],
                           (pair.get("rr_ci") or (None, None))[0],
                           (pair.get("rr_ci") or (None, None))[1])
        pair.update(ev)

    # Reliability tag from cohort N (with bigger thresholds since trajectories
    # are descriptive — the relevant N is the whole base)
    rel = assign_reliability(n_total, n_total)
    return {"qtype_block": "TRAJECTORY", "funnel": funnel, "base": base,
            "rows": rows, "n_total": n_total,
            "pair_comp": pair,
            "reliability": rel}


def build_block_comparative_adjusted(plan, cohort):
    b = _build_two_arm(plan, cohort)
    adjusters = plan.get("adjusters") or []
    adj = multivariate_ipw(b["group_a"], b["group_b"], adjusters,
                          b["label_a"], b["label_b"])
    gap = None
    if (b["comp"].get("abs_diff_pp") is not None
            and adj.get("adjusted_abs_diff_pp") is not None):
        gap = round(b["comp"]["abs_diff_pp"] - adj["adjusted_abs_diff_pp"], 1)
    adj["unadjusted_abs_diff_pp"] = b["comp"].get("abs_diff_pp")
    adj["gap_pp"] = gap
    b["adjusted"] = adj
    b["qtype_block"] = "COMPARATIVE-ADJUSTED"
    return b


def build_block_compound(plan, cohort):
    parts = plan.get("parts") or []
    return {"qtype_block": "COMPOUND",
            "parts": [dispatch_block_builder(p, cohort) for p in parts]}


def dispatch_block_builder(plan, cohort):
    qt = plan.get("qtype")
    builders = {
        "FACTUAL": build_block_factual,
        "DESCRIPTIVE": build_block_descriptive,
        "DESCRIPTIVE-TEMPORAL": build_block_descriptive_temporal,
        "COMPARATIVE": build_block_comparative,
        "TEMPORAL-CONDITIONAL": build_block_temporal_conditional,
        "PATHWAY-FUNNEL": build_block_pathway_funnel,
        "SUBGROUP-COMPARATIVE": build_block_subgroup_comparative,
        "TRAJECTORY": build_block_trajectory,
        "COMPARATIVE-ADJUSTED": build_block_comparative_adjusted,
        "COMPOUND": build_block_compound,
    }
    fn = builders.get(qt)
    if not fn: raise ValueError(f"unknown qtype: {qt}")
    return fn(plan, cohort)


# =====================================================================
# Synthesis + assembler
# =====================================================================

def _initial_direct_answer(question, block):
    qt = block.get("qtype_block")
    # Special: SUBGROUP-COMPARATIVE in stratified-descriptive mode
    if qt == "SUBGROUP-COMPARATIVE" and block.get("_subgroup_mode") == "stratified_descriptive":
        rows = block.get("stratified_descriptive_rows") or []
        if not rows:
            return "No strata available for this question."
        chi = block.get("chi_square_across_strata") or {}
        stratifier_name = (block.get("stratifier") or "strata").replace("_", " ")
        # Find the highest- and lowest-rate strata to lead the finding
        scored = [(r, r.get("rate_pct"))
                  for r in rows if r.get("rate_pct") is not None]
        if scored:
            scored.sort(key=lambda x: x[1], reverse=True)
            hi_row, hi_rate = scored[0]
            lo_row, lo_rate = scored[-1]
            spread = hi_rate - lo_rate
            if spread >= 15:
                direction_word = "varies sharply"
            elif spread >= 5:
                direction_word = "varies modestly"
            else:
                direction_word = "is roughly comparable"
            lead = (f"Functional outcome {direction_word} across "
                    f"{stratifier_name}: ranging from "
                    f"{hi_rate}% in {hi_row['stratum']} "
                    f"to {lo_rate}% in {lo_row['stratum']} "
                    f"(spread = {round(spread, 1)} pp).")
        else:
            lead = (f"Functional outcome across {stratifier_name}.")
        # Per-stratum summary (kept short, no nested CI to keep it readable)
        chunks = [lead, "By stratum:"]
        for r in rows:
            chunks.append(
                f" {r['stratum']}: N={r['N']}, {r['rate_pct']}% "
                f"({r['n_functional']}/{r['N']}) [{r.get('reliability','-')}];")
        chi_text = ""
        if chi.get("p_value") is not None:
            chi_p = chi["p_value"]
            verdict = ("rejects homogeneity (the gradient is unlikely to be chance)"
                       if chi_p < 0.05 else
                       "does not reject homogeneity (rates are not distinguishable)")
            chi_text = (f" Chi-square across strata: chi2={chi['chi2']}, "
                        f"df={chi['dof']}, p={chi_p}; this {verdict}.")
        return (" ".join(chunks).rstrip(";") + "."
                + chi_text
                + " No causal claim is supported; this is an observational "
                  "comparison at the association tier.")
    if qt in ("COMPARATIVE", "TEMPORAL-CONDITIONAL", "COMPARATIVE-ADJUSTED",
              "SUBGROUP-COMPARATIVE"):
        comp = block.get("comp", {})
        la, lb = block.get("label_a", "A"), block.get("label_b", "B")
        parts = [
            f"This analysis compares {la} (n={comp.get('n_a')}) and {lb} (n={comp.get('n_b')}).",
            (f"Functional outcomes were {comp.get('rate_a_pct')}% "
             f"({comp.get('k_a')}/{comp.get('n_a')}) for {la} and "
             f"{comp.get('rate_b_pct')}% ({comp.get('k_b')}/{comp.get('n_b')}) "
             f"for {lb}, an absolute difference of {(comp.get('abs_diff_pp') or 0):+} pp."),
            f"Risk ratio = {comp.get('rr')}. Fisher's exact p = {comp.get('fishers_exact_p')}.",
        ]
        if qt == "COMPARATIVE-ADJUSTED" and block.get("adjusted"):
            adj = block["adjusted"]
            parts.append(
                f"After multi-covariate IPW on {', '.join(adj.get('adjusters', []))}, "
                f"the contrast is {adj.get('adjusted_abs_diff_pp')} pp "
                f"(adjusted RR {adj.get('adjusted_rr')}); gap from unadjusted "
                f"is {adj.get('gap_pp')} pp.")
            parts.append("This is an adjusted observational comparison, not an identified causal effect.")
        else:
            parts.append("No causal claim is supported; this is an observational comparison at the association tier.")
        return " ".join(parts)
    if qt in ("DESCRIPTIVE", "DESCRIPTIVE-TEMPORAL"):
        n, rate, ci = block.get("n"), block.get("rate_pct"), block.get("ci_pct", (None, None))
        text = (f"The cohort matching the question's filter contains N={n} patients "
                f"with a functional rate of {rate}% [95% CI: {ci[0]}-{ci[1]}%].")
        if qt == "DESCRIPTIVE-TEMPORAL":
            t = block.get("time_to_event", {}); tgt = block.get("target_event", "event")
            if t.get("median_months") is not None:
                text += (f" Median time to {tgt}: {t['median_months']} months "
                        f"(IQR {t['iqr_months'][0]}-{t['iqr_months'][1]}; "
                        f"n={t['n_with_event']} with event).")
        return text
    if qt == "FACTUAL":
        return f"{block.get('label')}: {block.get('value')} patients."
    if qt == "TRAJECTORY":
        rows = block.get("rows", [])
        if not rows: return "No captured trajectories."
        top = rows[0]
        return (f"Among N={block.get('n_total')} patients with captured trajectories, "
                f"the most common is '{top['trajectory']}' (n={top['N']}, "
                f"{top['percent_of_cohort']}% of cohort) with functional rate {top['rate_pct']}%.")
    if qt == "PATHWAY-FUNNEL":
        rows = block.get("rows", [])
        if not rows: return "No pathway data."
        return (f"Across N={len(block.get('base', []))} patients, "
                + " | ".join(f"{r['pathway']}: {r['prevalence_pct']}% prevalence, "
                            f"{r['rate_pct']}% functional" for r in rows[:5]) + ".")
    if qt == "COMPOUND": return "Compound question; sub-answers below."
    return "Answer constructed."


def _gen_interp(question, locked, api_key, mode=None):
    """mode='stratified_descriptive' → use the stratified-descriptive prompt
    that focuses on the gradient, not on two-arm baseline imbalances."""
    if mode == "stratified_descriptive":
        prompt = STRATIFIED_DESC_INTERPRETATION_SYSTEM_PROMPT
    else:
        prompt = INTERPRETATION_SYSTEM_PROMPT
    r = _llm_json(prompt,
                 f"QUESTION: {question}\n\nLOCKED ANALYSIS BLOCK:\n{locked}\n\nWrite the interpretation.",
                 api_key, max_tokens=500)
    return r.get("interpretation") if "interpretation" in r else None


def _dedupe_against_locked(llm_caveats, locked_caveats):
    """Drop any LLM-generated caveat whose label matches a locked caveat
    (case-insensitive). This is the simple, reliable dedupe — the LLM is
    told not to duplicate, but it does anyway. Belt-and-suspenders."""
    locked_labels = {(c.get("label") or "").strip().lower()
                     for c in locked_caveats}
    deduped = []
    for c in llm_caveats:
        lbl = (c.get("label") or "").strip().lower()
        if lbl and lbl in locked_labels:
            continue
        deduped.append(c)
    return deduped


def _gen_caveats(question, locked, deterministic, api_key):
    det = "\n".join(f"  - [{c['label']}] {c['body']}" for c in deterministic)
    r = _llm_json(CAVEATS_SYSTEM_PROMPT,
                 f"QUESTION: {question}\n\nLOCKED BLOCK:\n{locked}\n\n"
                 f"DETERMINISTIC CAVEATS (do not duplicate):\n{det}\n\n"
                 f"Add 1-3 additional caveats.",
                 api_key, max_tokens=600)
    cav = r.get("additional_caveats") or []
    out = [{"label": c.get("label", "Caveat"), "body": c.get("body", ""),
            "anchor": c.get("anchor", ""), "locked": False}
           for c in cav if isinstance(c, dict)]
    return _dedupe_against_locked(out, deterministic)


def _apply_responsivity(question, answer, api_key, mode=None):
    """mode='stratified_descriptive' → use the stratified-descriptive prompt
    so the rewriter leads with the gradient finding, not per-arm Ns."""
    locked = [c for c in answer["caveats_and_limitations"] if c.get("locked")]
    llm_c = [c for c in answer["caveats_and_limitations"] if not c.get("locked")]
    payload = {"question": question, "qtype": answer.get("qtype"),
        "answer_object": {
            "direct_answer": answer["direct_answer"],
            "comparison_summary": (answer.get("outcomes_table") or {}).get("comparison_summary")
                                  or answer.get("comparison_summary"),
            "adjusted_analysis": answer.get("appendix_adjusted_analysis"),
            "stratified_descriptive": answer.get("stratified_descriptive"),
            "llm_caveats": llm_c,
        },
        "locked_caveats": [{"label": c["label"], "body": c["body"]} for c in locked]}
    if mode == "stratified_descriptive":
        prompt = STRATIFIED_DESC_RESPONSIVITY_SYSTEM_PROMPT
    else:
        prompt = RESPONSIVITY_SYSTEM_PROMPT
    r = _llm_json(prompt,
                 json.dumps(payload, indent=2, default=str), api_key, max_tokens=900)
    if "direct_answer" in r:
        answer["direct_answer"] = r["direct_answer"]
    reord = r.get("reordered_llm_caveats")
    if isinstance(reord, list):
        out = []
        for c in reord:
            if isinstance(c, dict):
                out.append({"label": c.get("label", ""), "body": c.get("body", ""),
                           "anchor": c.get("anchor", ""), "locked": False})
        out = _dedupe_against_locked(out, locked)
        answer["caveats_and_limitations"] = locked + out
    else:
        # Even if the LLM didn't reorder, still dedupe what we've got
        existing_llm = [c for c in answer["caveats_and_limitations"]
                        if not c.get("locked")]
        answer["caveats_and_limitations"] = (
            locked + _dedupe_against_locked(existing_llm, locked))
    answer["_responsivity_applied"] = "direct_answer" in r
    return answer


def assemble_answer(question, plan, block, api_key):
    qt_block = block.get("qtype_block")
    if qt_block == "COMPOUND":
        parts = []
        for sb, sp in zip(block.get("parts", []), plan.get("parts", [])):
            parts.append(assemble_answer(question, sp, sb, api_key))
        return {"question": question, "qtype": plan.get("qtype"),
                "router_plan": plan,
                "direct_answer": "This is a compound question; sub-answers below.",
                "sub_answers": parts,
                "n_total": sum(p.get("n_total", 0) for p in parts)}
    comp = block.get("comp")
    # For non-two-arm types (PATHWAY-FUNNEL, TRAJECTORY), fall back to pair_comp
    # so deterministic caveats (E-value, underpowered) still fire.
    comp_like = comp or block.get("pair_comp")
    evalue = ({"evalue_point": comp_like.get("evalue_point"),
              "evalue_ci_bound": comp_like.get("evalue_ci_bound")} if comp_like else None)
    # Stratified-descriptive packaged for both the locked block and the LLM
    is_strat_desc = (qt_block == "SUBGROUP-COMPARATIVE"
                     and block.get("_subgroup_mode") == "stratified_descriptive")
    strat_desc_payload = None
    if is_strat_desc:
        strat_desc_payload = {
            "stratifier": block.get("stratifier"),
            "rows": block.get("stratified_descriptive_rows") or [],
            "chi_square_across_strata":
                block.get("chi_square_across_strata") or {},
        }
    locked_text = render_locked_block(
        plan=plan, stats_summary=comp,
        outcomes_rows=block.get("outcomes_rows") or
                     [{"arm": r.get("trajectory") or r.get("pathway"),
                      "N": r["N"], "n_functional": r.get("n_functional"),
                      "rate_pct": r.get("rate_pct"), "ci_pct": r.get("ci_pct")}
                      for r in (block.get("rows") or [])],
        cohort_funnel=(block["funnel"].as_dict()
                      if isinstance(block.get("funnel"), CohortFunnel)
                      else block.get("funnel")),
        baseline=block.get("balance"),
        subgroups=block.get("subgroups") or
                  ({"by_stratifier": block.get("stratified")}
                   if block.get("stratified") else None),
        evalue=evalue, mde=block.get("mde"),
        followup=block.get("followup"), modality=block.get("modality"),
        adjusted=block.get("adjusted"), question_text=question,
        stratified_descriptive=strat_desc_payload,
    )
    # Build extra_rows for pathways/trajectories/strata caveats
    extra_rows = None
    qt_block_here = block.get("qtype_block")
    if qt_block_here == "PATHWAY-FUNNEL":
        extra_rows = [{"label": r["pathway"], "N": r["N"]}
                      for r in (block.get("rows") or [])]
    elif qt_block_here == "TRAJECTORY":
        extra_rows = [{"label": r["trajectory"], "N": r["N"]}
                      for r in (block.get("rows") or [])]
    elif qt_block_here == "SUBGROUP-COMPARATIVE" and \
            block.get("_subgroup_mode") == "stratified_descriptive":
        extra_rows = [{"label": r["stratum"], "N": r["N"]}
                      for r in (block.get("stratified_descriptive_rows") or [])]

    deterministic = build_deterministic_caveats(plan, comp_like,
                                                block.get("balance"),
                                                block.get("subgroups"), evalue,
                                                extra_rows=extra_rows)
    interp_mode = "stratified_descriptive" if is_strat_desc else None
    interp = _gen_interp(question, locked_text, api_key, mode=interp_mode) \
            or "Interpretation pass unavailable; see structured tables."
    llm_caveats = _gen_caveats(question, locked_text, deterministic, api_key)
    # n_total: prefer comp arms; fall back to block-level totals for non-two-arm
    if comp:
        n_total = comp.get("n_a", 0) + comp.get("n_b", 0)
    elif block.get("n_total") is not None:
        n_total = block["n_total"]
    elif block.get("n") is not None:
        n_total = block["n"]
    elif block.get("base"):
        n_total = len(block["base"])
    else:
        n_total = 0

    answer = {
        "question": question, "qtype": plan.get("qtype"), "router_plan": plan,
        "direct_answer": _initial_direct_answer(question, block),
        "cohort_construction": (block["funnel"].as_dict()
                               if isinstance(block.get("funnel"), CohortFunnel)
                               else block.get("funnel")),
        "reliability_tier": (block.get("reliability") or {}).get("tag") or "n/a",
        "n_total": n_total,
    }
    if block.get("outcomes_rows"):
        answer["outcomes_table"] = {
            "gloss": GLOSSES["outcomes_table"], "rows": block["outcomes_rows"],
            "comparison_summary": {**(comp or {}),
                                   "gloss": GLOSSES["comparison_summary"],
                                   "evalue_gloss": GLOSSES["evalue"]},
        }
    if block.get("subgroups"):
        answer["subgroup_detail"] = block["subgroups"]
    if block.get("stratified"):
        answer["subgroup_detail"] = {block["stratified"].get("stratifier_key"):
                                    block["stratified"]}
    if block.get("balance"):
        answer["appendix_baseline_differences"] = {
            "gloss": GLOSSES["baseline_differences"], "rows": block["balance"]}
    if block.get("adjusted"):
        answer["appendix_adjusted_analysis"] = {
            "gloss": GLOSSES["adjusted_analysis"], **block["adjusted"]}
    if qt_block in ("DESCRIPTIVE", "DESCRIPTIVE-TEMPORAL"):
        answer["descriptive_profile"] = block.get("profile")
        if qt_block == "DESCRIPTIVE-TEMPORAL":
            answer["time_to_event"] = block.get("time_to_event")
            answer["target_event"] = block.get("target_event")
    elif qt_block == "TRAJECTORY":
        answer["trajectory_ranking"] = {"rows": block.get("rows")}
    elif qt_block == "PATHWAY-FUNNEL":
        answer["pathway_funnel"] = {"rows": block.get("rows"),
                                    "headline_contrast": block.get("pair_comp")}
    elif qt_block == "FACTUAL":
        answer["factual_value"] = {"label": block.get("label"),
                                   "value": block.get("value")}
    if block.get("_subgroup_mode") == "stratified_descriptive":
        answer["stratified_descriptive"] = {
            "stratifier": block.get("stratifier"),
            "rows": block.get("stratified_descriptive_rows") or [],
            "chi_square_across_strata": block.get("chi_square_across_strata"),
        }
    answer["caveats_and_limitations"] = deterministic + llm_caveats
    answer["interpretation"] = interp
    answer["_numeric_grounding"] = verify_numeric_grounding(
        answer["direct_answer"] + " " + (interp or ""), locked_text)
    answer = _apply_responsivity(question, answer, api_key, mode=interp_mode)
    answer["_entity_recall"] = entity_recall_check(question, answer["direct_answer"])
    answer["_locked_block"] = locked_text
    return answer


# =====================================================================
# Public API
# =====================================================================

def _sparse_sentry(block, plan):
    """Refuse degenerate contrasts before they reach synthesis.

    Returns a refusal dict if the block is too sparse for inferential analysis,
    or None otherwise.
    """
    question = None
    funnel_dict = (block["funnel"].as_dict()
                  if isinstance(block.get("funnel"), CohortFunnel)
                  else block.get("funnel"))
    # Two-arm: any arm under 3
    if block.get("comp"):
        n_a, n_b = block["comp"]["n_a"], block["comp"]["n_b"]
        if min(n_a, n_b) < 3:
            return {"qtype": plan.get("qtype"), "router_plan": plan,
                    "direct_answer": (f"This comparison cannot be meaningfully run: "
                                     f"arm A N={n_a}, arm B N={n_b}. "
                                     f"At least 3 per arm needed."),
                    "cohort_construction": funnel_dict,
                    "reliability_tier": "Suppressed", "n_total": n_a + n_b,
                    "caveats_and_limitations": [{
                        "label": "Sparse cohort",
                        "body": f"arm A N={n_a}, arm B N={n_b}; below 3 per arm.",
                        "anchor": f"n_a={n_a}, n_b={n_b}", "locked": True}],
                    "_sparse_refusal": True}
    # PATHWAY-FUNNEL: any pathway under 3 OR the top two pathways under 3
    if block.get("qtype_block") == "PATHWAY-FUNNEL":
        min_n = block.get("min_pathway_n", 0)
        rows = block.get("rows", [])
        if min_n < 3 and rows:
            sparse_names = [r["pathway"] for r in rows if r["N"] < 3]
            return {"qtype": plan.get("qtype"), "router_plan": plan,
                    "direct_answer": (f"This pathway comparison cannot be meaningfully run: "
                                     f"the pathway(s) {', '.join(sparse_names)} have N<3. "
                                     f"All pathway prevalences are reported below for "
                                     f"context, but no inferential contrast is meaningful."),
                    "cohort_construction": funnel_dict,
                    "pathway_funnel": {"rows": rows, "headline_contrast": None},
                    "reliability_tier": "Suppressed", "n_total": sum(r["N"] for r in rows),
                    "caveats_and_limitations": [{
                        "label": "Sparse pathway",
                        "body": (f"Pathway(s) with N<3: {', '.join(sparse_names)}. "
                                 f"No headline contrast is reported."),
                        "anchor": f"min pathway N={min_n}", "locked": True}],
                    "_sparse_refusal": True}
    # TRAJECTORY: cohort under 3
    if block.get("qtype_block") == "TRAJECTORY":
        n_total = block.get("n_total", 0)
        if n_total < 3:
            return {"qtype": plan.get("qtype"), "router_plan": plan,
                    "direct_answer": (f"Trajectory analysis cannot be meaningfully run: "
                                     f"only {n_total} patients with captured trajectories. "
                                     f"At least 3 needed."),
                    "cohort_construction": funnel_dict,
                    "reliability_tier": "Suppressed", "n_total": n_total,
                    "caveats_and_limitations": [{
                        "label": "Sparse cohort",
                        "body": f"N={n_total}; below 3.",
                        "anchor": f"N={n_total}", "locked": True}],
                    "_sparse_refusal": True}
    return None


def answer_question(question, patients, api_key, verbose=False):
    """End-to-end: route -> dispatch -> assemble -> verify.

    Args:
        question: natural-language question
        patients: dict {pid -> patient_record} or list of records
        api_key:  OpenAI API key

    Returns the structured answer dict.
    """
    if not api_key:
        return {"question": question, "error": "missing_api_key",
                "failure_reason": "Provide an OpenAI API key to enable Q&A."}
    cohort = list(patients.values()) if isinstance(patients, dict) else list(patients)
    t0 = _time.time()
    r = route_question(question, api_key, max_retries=2)
    if not r["accepted"]:
        return {"question": question, "error": "router_failure",
                "failure_reason": r.get("failure_reason"),
                "router_retries": r.get("retries"),
                "duration_sec": round(_time.time() - t0, 2)}
    plan = r["plan"]
    if verbose: print(f"router: qtype={plan.get('qtype')}")
    try:
        block = dispatch_block_builder(plan, cohort)
    except Exception as e:
        return {"question": question, "qtype": plan.get("qtype"),
                "error": "executor_failure", "failure_reason": str(e),
                "router_plan": plan, "duration_sec": round(_time.time() - t0, 2)}
    # Sparse-cohort sentry: refuses degenerate contrasts for ALL block types.
    sparse = _sparse_sentry(block, plan)
    if sparse:
        sparse["question"] = question
        sparse["duration_sec"] = round(_time.time() - t0, 2)
        return sparse
    ans = assemble_answer(question, plan, block, api_key)
    ans["duration_sec"] = round(_time.time() - t0, 2)
    return ans
