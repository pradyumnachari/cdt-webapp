"""Visualizations — descriptive cohort statistics and treatment-flow
diagrams for the synthetic meningioma cohort.

Designed around two principles: simplicity and understanding. Every panel
answers an explicit clinical question, every label is plain language,
and the decision-level concept (L1 / L2 / L3) is explained where it is
first used.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Optional

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import nav, qa, style  # noqa: E402
from lib.bootstrap import get_cohort  # noqa: E402
from lib.buckets import (ACTION_COLORS, ACTION_LABELS,  # noqa: E402
                         OUTCOME_COLORS)
from lib.engine import cohort_stats  # noqa: E402
from lib.figures import build_action_outcome_sankey  # noqa: E402

st.set_page_config(page_title="Visualizations — Ask my data",
                   page_icon="🧠", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    </style>
""", unsafe_allow_html=True)
style.inject()
nav.render("viz")

# ─────────────────────────────────────────────────────────────────────────
# Hero
# ─────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero" style="padding:24px 4px 14px 4px;">
      <p class="hero-eyebrow">Visualizations</p>
      <h1 class="hero-title" style="font-size:1.85rem;">
        Who is in this cohort, how did they do, and how did they get
        there?</h1>
      <p class="hero-sub">
        The visualizations on this page are a structured way to look at
        the cohort end-to-end. The first block shows <i>who is in the
        cohort</i> after any filters you apply: how many patients, the
        split between functional and impaired outcomes, and how the
        filtered rate compares with the whole cohort. The second block
        shows <i>how they were treated</i>: the sequence of clinical
        decisions each patient went through, and which sequences are
        most common.
        <br/><br/>
        Use the filters at the top to narrow to a subgroup that matters
        to you — for instance, WHO grade 2 skull-base patients — and the
        page recomputes live. Hover any bar, ribbon, or row to see exact
        counts.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

cohort = get_cohort()
patients = cohort["patients"]

# ─────────────────────────────────────────────────────────────────────────
# Label maps — turn raw machine values into plain clinician language
# ─────────────────────────────────────────────────────────────────────────
_GRADE_LABEL = {
    "grade_1": "WHO grade 1", "grade_2": "WHO grade 2",
    "grade_3": "WHO grade 3",
}
_LOC_LABEL = {
    "skull_base": "Skull base", "convexity": "Convexity",
    "parasagittal": "Parasagittal", "sphenoid_wing": "Sphenoid wing",
    "other": "Other location",
}
_AGE_LABEL = {"<50": "Under 50", "50-65": "50 – 65", ">=65": "65 or older"}
_GENDER_LABEL = {"M": "Male", "F": "Female"}


def _disp(value: str, mapping: dict) -> str:
    return mapping.get(value, str(value).replace("_", " "))


# ─────────────────────────────────────────────────────────────────────────
# Readability layer for Sankey figures (defined up here so the legend
# strip below can colour its swatches from the same palette the diagrams
# use).
#
# Plotly's default Sankey labels are small and rendered with a faint halo
# against the saturated node fills, which makes them hard to read. On top
# of that, the upstream colour palette in buckets.py reuses the SAME hex
# (#16a34a) for both Watch & Wait (action) and Functional (outcome), which
# made the two visually identical. And the L2: Surgery node was getting
# drowned by green outgoing ribbons flowing to L3: Watch & Wait.
#
# Fix in this layer:
#   1. Assign node fills by LABEL (not by source hex), so Watch & Wait and
#      Functional get distinct pastels.
#   2. Surgery moves to pale purple — visually distinct from everything
#      else and from the green ribbons.
#   3. Force the node labels to solid near-black, larger size, heavier
#      font family.
# Link colours are not touched — they don't carry text.
# ─────────────────────────────────────────────────────────────────────────

_NODE_PALETTE = {
    "watch_and_wait":  "#bbf7d0",  # pale green (action: watch & wait)
    "surgery":         "#ddd6fe",  # pale purple (action: surgery — was blue)
    "radiation":       "#fecaca",  # pale red (action: radiation)
    "functional":      "#a5f3fc",  # pale cyan (outcome: functional)
    "impaired":        "#fed7aa",  # pale orange (outcome: impaired)
    "ended":           "#e2e8f0",  # pale grey (end-after-L1 / end-after-L2)
    "fallback":        "#e2e8f0",
}

_READABLE_TEXTFONT = dict(
    color="#0f172a",
    size=13,
    family=("system-ui, -apple-system, 'Segoe UI', Roboto, "
            "Helvetica, Arial, sans-serif"),
)


def _node_color_for(label: str) -> str:
    """Pick a readable pastel based on the node's display label."""
    lo = (label or "").lower()
    if "ended after" in lo:
        return _NODE_PALETTE["ended"]
    if "watch" in lo:
        return _NODE_PALETTE["watch_and_wait"]
    if "surgery" in lo:
        return _NODE_PALETTE["surgery"]
    if "radiation" in lo:
        return _NODE_PALETTE["radiation"]
    if "functional" in lo:
        return _NODE_PALETTE["functional"]
    if "impaired" in lo:
        return _NODE_PALETTE["impaired"]
    return _NODE_PALETTE["fallback"]


def _readable_sankey(fig):
    """Recolour node fills (label-based), make every link match its target
    node, and force dark, larger labels.

    Recolouring links is what stops the L3 → Functional ribbon from
    showing as green: the build step set its colour from the saturated
    OUTCOME_COLORS["functional"]=#16a34a, but the destination terminus
    is now the cyan pastel. Setting link.color so it tracks the target
    node makes every ribbon arrive in the same hue as its terminus.
    """
    if fig is None:
        return fig
    try:
        node = fig.data[0].node
        link = fig.data[0].link
        labels = list(node.label or [])

        # 1. Node fills: label-based pastel.
        node_colors = [_node_color_for(lbl) for lbl in labels]
        node.color = node_colors

        # 2. Link fills: rgba of the target node's pastel.
        def _rgba(hex_color: str, alpha: float = 0.6) -> str:
            h = hex_color.lstrip("#")
            if len(h) != 6:
                return hex_color
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return f"rgba({r},{g},{b},{alpha})"

        targets = list(link.target or [])
        link.color = [
            _rgba(node_colors[t]) if 0 <= t < len(node_colors)
            else _rgba("#e2e8f0")
            for t in targets
        ]

        # 3. Dark, larger labels.
        fig.update_traces(textfont=_READABLE_TEXTFONT)
    except Exception:  # noqa: BLE001 — defensive; never block rendering
        pass
    return fig


# ─────────────────────────────────────────────────────────────────────────
# Filters (multi-select; empty selection = all)
# ─────────────────────────────────────────────────────────────────────────
def _unique_values(path: tuple) -> list:
    vals = set()
    for r in patients.values():
        d = r
        for k in path:
            d = d[k]
        vals.add(d)
    return sorted(str(v) for v in vals)


def _on_reset():
    for k in ("flt_grade", "flt_loc", "flt_age", "flt_gender"):
        st.session_state[k] = []
    st.rerun()

f1, f2, f3, f4 = st.columns(4)
with f1:
    grade_sel = st.multiselect(
        "Grade",
        options=_unique_values(("stratification", "grade")),
        format_func=lambda v: _disp(v, _GRADE_LABEL),
        key="flt_grade",
        placeholder="All grades",
    )
with f2:
    loc_sel = st.multiselect(
        "Location",
        options=_unique_values(("stratification", "location")),
        format_func=lambda v: _disp(v, _LOC_LABEL),
        key="flt_loc",
        placeholder="All locations",
    )
with f3:
    age_sel = st.multiselect(
        "Age band",
        options=_unique_values(("stratification", "age")),
        format_func=lambda v: _disp(v, _AGE_LABEL),
        key="flt_age",
        placeholder="All age bands",
    )
with f4:
    gender_sel = st.multiselect(
        "Gender",
        options=_unique_values(("stratification", "gender")),
        format_func=lambda v: _disp(v, _GENDER_LABEL),
        key="flt_gender",
        placeholder="All",
    )

reset_col, _spacer = st.columns([1, 6])
with reset_col:
    st.button("Reset filters", on_click=_on_reset,
              type="secondary", use_container_width=True)


def _keep(r: dict) -> bool:
    s = r["stratification"]
    return ((not grade_sel or s["grade"] in grade_sel)
            and (not loc_sel or s["location"] in loc_sel)
            and (not age_sel or s["age"] in age_sel)
            and (not gender_sel or s["gender"] in gender_sel))


filtered = {p: r for p, r in patients.items() if _keep(r)}

# Filter-impact strip
n_total = len(patients)
n_filt = len(filtered)
frac = (n_filt / n_total * 100) if n_total else 0
is_filtered = (n_filt != n_total)

if is_filtered:
    st.markdown(
        f"<div style='background:#eff6ff;border-left:3px solid #2563eb;"
        f"padding:10px 14px;border-radius:4px;margin-top:6px;"
        f"font-size:13px;color:#1e3a5f;display:flex;align-items:center;"
        f"justify-content:space-between;flex-wrap:wrap;gap:8px;'>"
        f"<span>🔽 Showing <b style='font-size:14px;'>{n_filt:,}</b> of "
        f"<b>{n_total:,}</b> patients "
        f"(<b>{frac:.1f}%</b> of cohort).</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    clear_filters_col, _ = st.columns([1, 6])
    with clear_filters_col:
        st.button("Clear filters", on_click=_on_reset, key="clear_filters_inline",
                  type="secondary", use_container_width=True)
else:
    st.markdown(
        f"<div class='info-line' style='margin-top:6px;font-size:13px;'>"
        f"Showing <b>{n_filt:,}</b> of <b>{n_total:,}</b> patients "
        f"({frac:.0f}% of cohort).</div>",
        unsafe_allow_html=True,
    )

if not filtered:
    st.warning("No patients match the current filters. Use **Reset "
               "filters** above to start over.")
    style.footer()
    st.stop()


# ─────────────────────────────────────────────────────────────────────────
# Cohort summary — composition (left) + functional rate (right)
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label' style='margin-top:24px;'>"
            "Treatment pathways</p>", unsafe_allow_html=True)
st.markdown(
    """
    <div style='display:grid;grid-template-columns:1fr 1fr;
                gap:12px;margin-bottom:16px;'>
      <div style='border:1px solid #e2e8f0;border-radius:10px;
                  padding:14px 16px;background:#f8fafc;'>
        <div style='font-size:11px;font-weight:700;text-transform:uppercase;
                    letter-spacing:0.09em;color:#475569;margin-bottom:8px;'>
          Tumour size
        </div>
        <div style='display:flex;flex-direction:column;gap:6px;
                    font-size:13px;color:#334155;'>
          <div><span style='font-weight:700;color:#0f172a;'>Small</span>
            — tumour under 2 cm</div>
          <div><span style='font-weight:700;color:#0f172a;'>Medium</span>
            — tumour 2 – 4 cm</div>
          <div><span style='font-weight:700;color:#0f172a;'>Large</span>
            — tumour 4 cm or more</div>
        </div>
      </div>
      <div style='border:1px solid #e2e8f0;border-radius:10px;
                  padding:14px 16px;background:#f8fafc;'>
        <div style='font-size:11px;font-weight:700;text-transform:uppercase;
                    letter-spacing:0.09em;color:#475569;margin-bottom:8px;'>
          Symptoms at presentation
        </div>
        <div style='display:flex;flex-direction:column;gap:6px;
                    font-size:13px;color:#334155;'>
          <div><span style='font-weight:700;color:#0f172a;'>None</span>
            — asymptomatic at presentation</div>
          <div><span style='font-weight:700;color:#0f172a;'>Present</span>
            — symptomatic at presentation (e.g. headache, seizure,
            focal deficit)</div>
        </div>
      </div>
    </div>
    <div style='font-size:12.5px;color:#475569;margin-bottom:14px;
                font-style:italic;'>
      Example: "medium none" = tumour 3–5 cm, asymptomatic at presentation.
    </div>
    """,
    unsafe_allow_html=True,
)

stats = cohort_stats(filtered)
baseline = cohort_stats(patients)

# Outcome composition
n_known = stats["n_outcome_known"]
n_func = stats["n_functional"]
n_imp = n_known - n_func
n_unknown = stats["n"] - n_known
rate = stats["functional_rate"]
ci_lo, ci_hi = qa.clopper_pearson(n_func, n_known) if n_known else (0, 0)
baseline_rate = baseline["functional_rate"]


def _seg(label: str, n: int, total: int, color: str) -> str:
    if total <= 0 or n <= 0:
        return ""
    pct = n / total * 100
    return (f"<div style='flex:{n};background:{color};height:14px;"
            f"display:flex;align-items:center;justify-content:center;"
            f"font-size:10.5px;color:white;font-weight:700;' "
            f"title='{label}: {n} ({pct:.0f}%)'>{n}</div>")


bar_total = max(stats["n"], 1)
composition_bar = (
    f"<div style='display:flex;width:100%;border-radius:6px;"
    f"overflow:hidden;border:1px solid #e2e8f0;margin-top:8px;'>"
    + _seg("Functional", n_func, bar_total, "#16a34a")
    + _seg("Impaired", n_imp, bar_total, "#ea580c")
    + _seg("Unknown", n_unknown, bar_total, "#94a3b8")
    + "</div>"
)
composition_legend = (
    f"<div style='display:flex;gap:14px;margin-top:8px;font-size:12.5px;"
    f"color:#475569;'>"
    f"<span><span style='display:inline-block;width:10px;height:10px;"
    f"background:#16a34a;border-radius:2px;margin-right:5px;'></span>"
    f"Functional ({n_func})</span>"
    f"<span><span style='display:inline-block;width:10px;height:10px;"
    f"background:#ea580c;border-radius:2px;margin-right:5px;'></span>"
    f"Impaired ({n_imp})</span>"
    + (f"<span><span style='display:inline-block;width:10px;height:10px;"
       f"background:#94a3b8;border-radius:2px;margin-right:5px;'></span>"
       f"Unknown ({n_unknown})</span>" if n_unknown else "")
    + "</div>"
)

block_l, block_r = st.columns([1.1, 1])

with block_l:
    st.markdown(
        f"""
        <div class='stat-card' style='padding:14px 16px;'>
          <p class='stat-card-label'>Patients</p>
          <p class='stat-card-value' style='font-size:1.6rem;'>{stats['n']:,}</p>
          {composition_bar}
          {composition_legend}
        </div>
        """,
        unsafe_allow_html=True,
    )

with block_r:
    if rate is not None:
        rate_pct = f"{rate * 100:.1f}%"
        ci_str = (f"95% CI: {ci_lo * 100:.1f}% – {ci_hi * 100:.1f}%"
                  if n_known else "")
        if is_filtered and baseline_rate is not None:
            delta = (rate - baseline_rate) * 100
            arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "—")
            arrow_color = ("#16a34a" if delta > 0
                           else ("#dc2626" if delta < 0 else "#64748b"))
            baseline_line = (
                f"<div style='font-size:12.5px;color:#475569;"
                f"margin-top:6px;'>"
                f"vs. {baseline_rate * 100:.1f}% in the full "
                f"{baseline['n']:,}-patient cohort "
                f"<span style='color:{arrow_color};font-weight:600;'>"
                f"{arrow} {abs(delta):.1f} pp</span></div>"
            )
        else:
            baseline_line = (
                f"<div style='font-size:12.5px;color:#475569;"
                f"margin-top:6px;'>Across the full cohort.</div>"
            )
    else:
        rate_pct = "—"
        ci_str = "no patients with a recorded outcome"
        baseline_line = ""

    st.markdown(
        f"""
        <div class='stat-card' style='padding:14px 16px;'>
          <p class='stat-card-label'>Functional at last follow-up</p>
          <p class='stat-card-value' style='font-size:1.6rem;'>{rate_pct}</p>
          <div style='font-size:12.5px;color:#475569;'>{ci_str}</div>
          {baseline_line}
        </div>
        """,
        unsafe_allow_html=True,
    )

# Inline "what does functional mean?" explainer (popover; compact)
with st.popover("What does *functional* mean here?", use_container_width=False):
    st.markdown(
        """
        **Functional** = ECOG performance status of 0–2 *or* Karnofsky
        Performance Score (KPS) ≥ 70 at the last recorded follow-up.
        That covers patients who are independent in self-care and most
        daily activities, even if they have residual symptoms.

        **Impaired** = ECOG 3–4 *or* KPS < 70: needing substantial help
        with daily activities.

        **Unknown** = the chart did not record a usable performance
        score at the last follow-up.

        Source: extracted from the longitudinal notes by the v9
        extraction pipeline.
        """
    )


# ─────────────────────────────────────────────────────────────────────────
# Decision-level explainer — appears immediately before "Treatment pathways"
# because the levels concept is what the pathway view is built on.
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label' style='margin-top:30px;'>"
            "What are decision levels (L1 · L2 · L3)?</p>",
            unsafe_allow_html=True)
st.markdown(
    """
    <div class='info-line' style='font-size:13.5px;line-height:1.6;'>
      Every patient's pathway is divided into <b>sequential decision
      points</b>. Each level is one moment where a clinician chooses
      among watch-and-wait, surgery, and radiation.
      <ul style='margin:8px 0 0 18px;padding:0;color:#334155;'>
        <li><b>L1</b> — the first treatment decision after diagnosis.</li>
        <li><b>L2</b> — the next decision, typically months or years
          later (recurrence, growth on imaging, new symptoms).</li>
        <li><b>L3</b> — a third decision if the patient reaches one.
          Many patients never do.</li>
      </ul>
      <div style='margin-top:8px;color:#475569;font-size:12.5px;'>
        Consecutive same-action events (e.g. years of stable
        surveillance) are collapsed into one level.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────
# Treatment pathways — three tabs, each answering a distinct question
# ─────────────────────────────────────────────────────────────────────────
st.markdown("<p class='section-label' style='margin-top:24px;'>"
            "Treatment pathways</p>", unsafe_allow_html=True)

st.markdown(
    """
    <div style='font-size:13.5px;color:#334155;line-height:1.6;
                margin:0 0 16px 0;'>
      A <b>treatment pathway</b> is the ordered sequence of decisions a
      patient went through. The three views below let you look at the
      same pathways from different angles:
    </div>
    <div style='display:grid;grid-template-columns:1fr 1fr 1fr;
                gap:12px;margin-bottom:16px;'>
      <div style='border:1px solid #bfdbfe;border-radius:10px;
                  padding:14px 16px;background:#eff6ff;'>
        <div style='font-size:11px;font-weight:700;text-transform:uppercase;
                    letter-spacing:0.09em;color:#2563eb;margin-bottom:6px;'>
          Initial state → first treatment → outcome
        </div>
        <div style='font-size:13px;color:#334155;line-height:1.55;'>
          How the patient's clinical state at presentation (tumour size,
          symptoms) connected to the L1 decision and to the eventual
          functional outcome. Thicker ribbons = more patients.
        </div>
       
      </div>
      <div style='border:1px solid #ddd6fe;border-radius:10px;
                  padding:14px 16px;background:#f5f3ff;'>
        <div style='font-size:11px;font-weight:700;text-transform:uppercase;
                    letter-spacing:0.09em;color:#7c3aed;margin-bottom:6px;'>
          Full trajectory (L1 → L2 → L3 → outcome)
        </div>
        <div style='font-size:13px;color:#334155;line-height:1.55;'>
          The complete sequence of decisions across all three levels.
          Look for the dominant ribbons (most common pathways) and
          where flows diverge or recombine.
        </div>
       
      </div>
      <div style='border:1px solid #bbf7d0;border-radius:10px;
                  padding:14px 16px;background:#f0fdf4;'>
        <div style='font-size:11px;font-weight:700;text-transform:uppercase;
                    letter-spacing:0.09em;color:#16a34a;margin-bottom:6px;'>
          Top trajectories ranked
        </div>
        <div style='font-size:13px;color:#334155;line-height:1.55;'>
          The most common end-to-end pathways listed as a table, with
          how often each occurred and the functional-outcome rate
          within each.
        </div>
        
      </div>
    </div>
    <div style='font-size:13px;color:#475569;margin-bottom:12px;
                font-style:italic;'>
      Together: what treatment patterns are most common, and which are
      associated with the best (or worst) functional outcomes?
    </div>
    """,
    unsafe_allow_html=True,
)
# Color-legend strip above the Sankeys — the swatch colours mirror the
# pastel palette the readability layer applies to every Sankey node, so
# users can read the diagram directly off this strip.
def _swatch(color: str, label: str) -> str:
    return (
        f"<span style='display:inline-flex;align-items:center;"
        f"margin-right:18px;'>"
        f"<span style='display:inline-block;width:14px;height:14px;"
        f"background:{color};border:1px solid #cbd5e1;border-radius:3px;"
        f"margin-right:6px;'></span>{label}</span>"
    )

st.markdown(
    f"""
    <div style='display:flex;flex-wrap:wrap;gap:4px 0;margin:0 0 10px 0;
                font-size:13px;color:#334155;'>
      {_swatch(_NODE_PALETTE['watch_and_wait'], 'Watch and wait')}
      {_swatch(_NODE_PALETTE['surgery'],        'Surgery')}
      {_swatch(_NODE_PALETTE['radiation'],      'Radiation')}
      {_swatch(_NODE_PALETTE['functional'],     'Functional outcome')}
      {_swatch(_NODE_PALETTE['impaired'],       'Impaired outcome')}
      {_swatch(_NODE_PALETTE['ended'],          'Ended (no further treatment)')}
    </div>
    """,
    unsafe_allow_html=True,
)

recs = list(filtered.values())


def _action_seq(p: dict) -> List[str]:
    levels = p.get("levels", {})
    return [levels[lv]["action"] for lv in sorted(levels)]


def _func(p: dict) -> str:
    return p.get("outcome", {}).get("functional_status", "unknown")


def _hex_to_rgba(hex_color: str, alpha: float = 0.55) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"
    return hex_color


def build_l1_l2_l3_sankey(records: List[dict]) -> Optional[go.Figure]:
    """Sankey covering up to three sequential decision levels + outcome.

    A patient who only reaches L1 (then ends) is routed: L1 → "ended after L1"
    → outcome. A patient who reaches L1 + L2 is routed: L1 → L2 → "ended
    after L2" → outcome. A patient who reaches L1 + L2 + L3: L1 → L2 → L3 →
    outcome. The end-after sentinels prevent the Sankey from misleadingly
    suggesting a third treatment happened when it didn't.
    """
    paths = defaultdict(int)   # (L1, L2_or_end, L3_or_end, outcome) -> count
    end_color = "#cbd5e1"
    end_after_l1 = "ended after L1"
    end_after_l2 = "ended after L2"
    end_after_l3 = "ended after L3"
    for p in records:
        seq = _action_seq(p)
        out = _func(p)
        if not seq:
            continue
        l1 = seq[0]
        l2 = seq[1] if len(seq) > 1 else end_after_l1
        l3 = seq[2] if len(seq) > 2 else (end_after_l2 if len(seq) > 1 else None)
        if l3 is None:
            # The patient ended at L1 — the L2 column shows the sentinel,
            # the L3 column shows the L2 sentinel again so the flow has
            # somewhere to go before reaching outcome.
            l3 = end_after_l1
        elif len(seq) <= 2:
            # patient ended at L2
            l3 = end_after_l2
        paths[(l1, l2, l3, out)] += 1

    if not paths:
        return None

    nodes: list = []
    node_idx: dict = {}

    def node(label: str, color: str) -> int:
        if label not in node_idx:
            node_idx[label] = len(nodes)
            nodes.append({"label": label, "color": color})
        return node_idx[label]

    def label_for(action: str, level: int) -> str:
        if action.startswith("ended after"):
            return action
        return f"L{level}: {ACTION_LABELS.get(action, action)}"

    def color_for(action: str) -> str:
        if action.startswith("ended after"):
            return end_color
        return ACTION_COLORS.get(action, "#94a3b8")

    sources, targets, values, link_colors = [], [], [], []
    # Aggregate counts at each transition
    l1_to_l2 = defaultdict(int)
    l2_to_l3 = defaultdict(int)
    l3_to_out = defaultdict(int)
    for (l1, l2, l3, out), c in paths.items():
        l1_to_l2[(l1, l2)] += c
        l2_to_l3[(l1, l2, l3)] += c
        l3_to_out[(l1, l2, l3, out)] += c

    for (l1, l2), c in l1_to_l2.items():
        a = node(f"{label_for(l1, 1)}__L1", color_for(l1))
        b = node(f"{label_for(l2, 2)}__L2_after_{l1}", color_for(l2))
        sources.append(a); targets.append(b); values.append(c)
        link_colors.append(_hex_to_rgba(color_for(l2), 0.5))

    for (l1, l2, l3), c in l2_to_l3.items():
        b = node(f"{label_for(l2, 2)}__L2_after_{l1}", color_for(l2))
        e = node(f"{label_for(l3, 3)}__L3_after_{l1}_{l2}", color_for(l3))
        sources.append(b); targets.append(e); values.append(c)
        link_colors.append(_hex_to_rgba(color_for(l3), 0.5))

    for (l1, l2, l3, out), c in l3_to_out.items():
        e = node(f"{label_for(l3, 3)}__L3_after_{l1}_{l2}", color_for(l3))
        o = node(f"{out.title()}__out_{l1}_{l2}_{l3}",
                 OUTCOME_COLORS.get(out, "#94a3b8"))
        sources.append(e); targets.append(o); values.append(c)
        link_colors.append(_hex_to_rgba(OUTCOME_COLORS.get(out, "#94a3b8"), 0.5))

    if not sources:
        return None

    display_labels = [n["label"].split("__")[0] for n in nodes]
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=20, thickness=18, label=display_labels,
            color=[n["color"] for n in nodes],
            line=dict(width=0),
            hovertemplate="%{label}<br>n = %{value}<extra></extra>",
        ),
        link=dict(source=sources, target=targets, value=values,
                  color=link_colors),
    ))
    fig.update_layout(
        title=dict(text="<b>L1 → L2 → L3 → Outcome</b>",
                   font=dict(size=13, color="#0f172a")),
        height=560, margin=dict(t=44, b=10, l=10, r=10),
        font=dict(size=11.5, color="#0f172a"), paper_bgcolor="white",
    )
    return fig


def build_top_trajectories_table(records: List[dict],
                                  top_n: int = 12) -> Optional[dict]:
    """Most common end-to-end trajectories with N and functional rate."""
    counter: Counter = Counter()
    out_by_traj: dict = defaultdict(lambda: {"functional": 0, "impaired": 0,
                                              "unknown": 0})
    n_total = 0
    for p in records:
        seq = _action_seq(p)
        if not seq:
            continue
        traj = " → ".join(ACTION_LABELS.get(a, a) for a in seq)
        counter[traj] += 1
        out_by_traj[traj][_func(p)] += 1
        n_total += 1
    if not counter:
        return None
    rows = []
    for traj, n in counter.most_common(top_n):
        n_f = out_by_traj[traj]["functional"]
        n_i = out_by_traj[traj]["impaired"]
        n_known = n_f + n_i
        rate = (n_f / n_known) if n_known else None
        rows.append({
            "Trajectory": traj,
            "N": n,
            "% of cohort": f"{(n / n_total * 100):.1f}%",
            "Functional rate":
                (f"{rate * 100:.1f}%" if rate is not None else "—"),
        })
    return {"rows": rows, "n_total": n_total,
            "n_unique": len(counter)}


tab1, tab2, tab3 = st.tabs([
    "Initial state → first treatment → outcome",
    "Full trajectory (L1 → L2 → L3 → outcome)",
    "Top trajectories ranked",
])

with tab1:
    st.markdown(
        "<div style='font-size:13px;color:#475569;margin-bottom:6px;'>"
        "Given how a patient looked at presentation (tumour size, "
        "symptoms), what did the clinician choose at L1 and how did the "
        "patient do at last follow-up?</div>",
        unsafe_allow_html=True,
    )
    fig1 = _readable_sankey(build_action_outcome_sankey(recs))
    if fig1 is not None:
        st.plotly_chart(fig1, use_container_width=True)
    else:
        st.caption("No pathway data for this filter.")

with tab2:
    st.markdown(
        "<div style='font-size:13px;color:#475569;margin-bottom:6px;'>"
        "The full sequence of decisions for each patient: the first "
        "treatment (L1), the next decision (L2), a third decision if "
        "the patient reached one (L3), and the functional outcome at "
        "last follow-up. \"Ended after L<i>n</i>\" means the patient "
        "did not reach a further decision.</div>",
        unsafe_allow_html=True,
    )
    fig2 = _readable_sankey(build_l1_l2_l3_sankey(recs))
    if fig2 is not None:
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.caption("No pathway data for this filter.")

with tab3:
    st.markdown(
        "<div style='font-size:13px;color:#475569;margin-bottom:6px;'>"
        "Most common end-to-end trajectories. The functional rate within "
        "each row is computed only over patients with a known outcome.</div>",
        unsafe_allow_html=True,
    )
    cap = 12
    tt = build_top_trajectories_table(recs, top_n=cap)
    if tt is None:
        st.caption("No pathway data for this filter.")
    else:
        import pandas as pd
        df = pd.DataFrame(tt["rows"])
        st.dataframe(df, use_container_width=True, hide_index=True)
        n_unique = tt["n_unique"]
        n_patients = tt["n_total"]
        if n_unique <= cap:
            st.caption(
                f"{n_unique} unique trajectories across "
                f"{n_patients:,} patients; all are shown."
            )
        else:
            st.caption(
                f"{n_unique} unique trajectories across "
                f"{n_patients:,} patients; the top {cap} are shown."
            )


style.footer()
