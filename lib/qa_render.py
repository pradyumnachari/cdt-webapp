"""
Streamlit renderer for qa_v9 structured answers.

Single entrypoint: render_answer(answer_dict, st).
Renders all panels matching the screenshot layout:
  - direct answer card (with reliability + qtype badges)
  - cohort construction funnel table
  - outcomes table per arm with 95% CI
  - comparison summary line (abs diff, RR + CI, Fisher p, E-value)
  - subgroup detail panels (by grade / age / location) with reliability badges +
    Cochran-Mantel-Haenszel pooled OR
  - interpretation paragraph
  - caveats list with locked-vs-LLM markers
  - collapsible appendix: baseline differences (SMD table) + adjusted analysis
  - debug toggle: raw locked block, router plan, verifier output
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd


# =====================================================================
# Public entrypoint
# =====================================================================

def render_answer(answer: Dict[str, Any], st) -> None:
    """Render a qa_v9 answer dict as a sequence of Streamlit components."""
    if answer.get("error"):
        _render_error(answer, st); return

    if answer.get("sub_answers"):
        _render_compound(answer, st); return

    _render_direct_answer(answer, st)
    _render_cohort_construction(answer, st)
    _render_outcomes_table(answer, st)
    _render_subgroup_detail(answer, st)
    _render_interpretation(answer, st)
    _render_caveats(answer, st)
    _render_appendix(answer, st)
    _render_debug(answer, st)


# =====================================================================
# Direct answer + headline badges
# =====================================================================

_RELIABILITY_BADGE_COLOR = {
    "Adequate": "#16a34a",      # green
    "Limited": "#ca8a04",        # yellow
    "Underpowered": "#dc2626",  # red
    "Suppressed": "#94a3b8",    # gray
    "n/a": "#94a3b8",
}

_QTYPE_BADGE_COLOR = "#2563eb"  # blue


def _badge(label: str, color: str) -> str:
    return (f"<span style='display:inline-block;padding:2px 9px;"
            f"font-size:11px;font-weight:600;border-radius:999px;"
            f"background:{color}15;color:{color};margin-right:6px;"
            f"border:1px solid {color}40;'>{label}</span>")


def _render_direct_answer(answer: Dict[str, Any], st) -> None:
    qtype = answer.get("qtype") or "?"
    rel = answer.get("reliability_tier") or "n/a"
    n = answer.get("n_total", 0)
    rel_color = _RELIABILITY_BADGE_COLOR.get(rel, "#94a3b8")

    badges = (_badge(qtype, _QTYPE_BADGE_COLOR)
              + _badge(f"Reliability: {rel}", rel_color)
              + _badge(f"N={n}", "#475569"))

    st.markdown(
        f"""
        <div class="qa-card" style="border-left:3px solid #2563eb;
            padding:14px 16px;background:#f8fafc;border-radius:8px;margin-top:6px;">
          <div style="margin-bottom:6px;">{badges}</div>
          <div style="font-size:14.5px;color:#0f172a;line-height:1.55;">
            {answer.get("direct_answer", "")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =====================================================================
# Cohort construction funnel
# =====================================================================

def _render_cohort_construction(answer: Dict[str, Any], st) -> None:
    funnel = answer.get("cohort_construction")
    if not funnel: return
    rows = funnel.get("rows") or []
    if not rows: return
    st.markdown("<p class='section-label' style='margin-top:18px;'>Cohort construction</p>",
                unsafe_allow_html=True)
    df = pd.DataFrame([
        {"Inclusion criterion": r["step_description"],
         "N": r["N"],
         "Δ from previous step": (f"{r['delta_from_prev']:+d}"
                                 if isinstance(r.get("delta_from_prev"), int) else "")}
        for r in rows
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)


# =====================================================================
# Outcomes table + comparison summary
# =====================================================================

def _render_outcomes_table(answer: Dict[str, Any], st) -> None:
    # Stratified-descriptive SUBGROUP-COMPARATIVE has its own panel
    if answer.get("stratified_descriptive"):
        _render_stratified_descriptive(answer, st)
        return
    table = answer.get("outcomes_table")
    if not table:
        # Could be DESCRIPTIVE / TRAJECTORY / PATHWAY-FUNNEL / FACTUAL
        _render_descriptive_outputs(answer, st)
        return
    st.markdown("<p class='section-label' style='margin-top:18px;'>Functional outcomes by arm</p>",
                unsafe_allow_html=True)
    rows = table.get("rows") or []
    df = pd.DataFrame([
        {"Arm": r["arm"], "N": r["N"], "Functional": r["n_functional"],
         "Rate": f"{r['rate_pct']}%",
         "95% CI (Clopper-Pearson)": f"{r['ci_pct'][0]}%–{r['ci_pct'][1]}%"}
        for r in rows
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    cs = table.get("comparison_summary") or {}
    if cs:
        diff = cs.get("abs_diff_pp")
        diff_ci = cs.get("abs_diff_ci_pp") or (None, None)
        rr = cs.get("rr")
        rr_ci = cs.get("rr_ci") or (None, None)
        fp = cs.get("fishers_exact_p")
        ev = cs.get("evalue_point")
        st.markdown(
            f"""
            <div style="margin-top:10px;padding:10px 14px;background:#f1f5f9;
                       border-radius:6px;font-size:13px;color:#0f172a;">
              <b>Absolute difference:</b> {diff:+ if isinstance(diff,(int,float)) else ''} pp
                ({diff_ci[0]} to {diff_ci[1]} pp).
              &nbsp;&nbsp;<b>Risk ratio:</b> {rr} ({rr_ci[0]}–{rr_ci[1]}).
              &nbsp;&nbsp;<b>Fisher's exact p:</b> {fp}.
              &nbsp;&nbsp;<b>E-value:</b> {ev}.
            </div>
            """.replace("None", "—"),
            unsafe_allow_html=True,
        )


def _render_stratified_descriptive(answer: Dict[str, Any], st) -> None:
    """Per-stratum N + functional rate + CI + reliability + chi-square test."""
    sd = answer["stratified_descriptive"]
    rows = sd.get("rows") or []
    if not rows: return
    title = (sd.get("stratifier") or "stratifier").replace("_", " ").title()
    st.markdown(f"<p class='section-label' style='margin-top:18px;'>"
                f"Functional outcomes by {title}</p>",
                unsafe_allow_html=True)
    df = pd.DataFrame([{
        "Stratum": r["stratum"], "N": r["N"], "Functional": r["n_functional"],
        "Impaired": r["n_impaired"],
        "Rate": (f"{r['rate_pct']}%" if r.get('rate_pct') is not None else "—"),
        "95% CI (Clopper-Pearson)":
            (f"{r['ci_pct'][0]}%–{r['ci_pct'][1]}%"
             if r.get('rate_pct') is not None else "—"),
        "Reliability": r.get("reliability", "n/a"),
    } for r in rows])
    st.dataframe(df, use_container_width=True, hide_index=True)
    chi = sd.get("chi_square_across_strata") or {}
    if chi.get("p_value") is not None:
        st.markdown(
            f"""<div style='margin-top:10px;padding:10px 14px;background:#f1f5f9;
            border-radius:6px;font-size:13px;'>
            <b>Chi-square test for variation across strata:</b>
            chi² = {chi['chi2']}, df = {chi['dof']}, p = {chi['p_value']}
            ({chi['strata_used']} strata included).
            </div>""",
            unsafe_allow_html=True,
        )


def _render_descriptive_outputs(answer: Dict[str, Any], st) -> None:
    """Render outputs for non-two-arm qtypes: DESCRIPTIVE, TRAJECTORY,
    PATHWAY-FUNNEL, FACTUAL."""
    qtype = answer.get("qtype")
    if answer.get("descriptive_profile"):
        st.markdown("<p class='section-label' style='margin-top:18px;'>Cohort profile</p>",
                    unsafe_allow_html=True)
        df = pd.DataFrame(answer["descriptive_profile"])
        st.dataframe(df, use_container_width=True, hide_index=True)
        if answer.get("time_to_event"):
            t = answer["time_to_event"]
            if t.get("median_months") is not None:
                tgt = answer.get("target_event", "event")
                st.markdown(
                    f"<div style='margin-top:8px;padding:8px 12px;"
                    f"background:#f1f5f9;border-radius:6px;font-size:13px;'>"
                    f"<b>Median time to {tgt}:</b> {t['median_months']} months "
                    f"(IQR {t['iqr_months'][0]}–{t['iqr_months'][1]}); "
                    f"n={t['n_with_event']} with event.</div>",
                    unsafe_allow_html=True,
                )
    if answer.get("trajectory_ranking"):
        st.markdown("<p class='section-label' style='margin-top:18px;'>Trajectory ranking</p>",
                    unsafe_allow_html=True)
        rows = answer["trajectory_ranking"].get("rows") or []
        df = pd.DataFrame([{
            "Trajectory": r["trajectory"], "N": r["N"],
            "% of cohort": f"{r['percent_of_cohort']}%",
            "Functional rate": (f"{r['rate_pct']}% "
                               f"[{r['ci_pct'][0]}–{r['ci_pct'][1]}%]"
                               if r.get('rate_pct') is not None else "—"),
        } for r in rows])
        st.dataframe(df, use_container_width=True, hide_index=True)
    if answer.get("pathway_funnel"):
        st.markdown("<p class='section-label' style='margin-top:18px;'>Pathway funnel</p>",
                    unsafe_allow_html=True)
        rows = answer["pathway_funnel"].get("rows") or []
        df = pd.DataFrame([{
            "Pathway": r["pathway"], "N": r["N"],
            "Prevalence": f"{r['prevalence_pct']}%",
            "Functional rate": (f"{r['rate_pct']}% "
                               f"[{r['ci_pct'][0]}–{r['ci_pct'][1]}%]"
                               if r.get('rate_pct') is not None else "—"),
        } for r in rows])
        st.dataframe(df, use_container_width=True, hide_index=True)
        hl = answer["pathway_funnel"].get("headline_contrast") or {}
        if hl.get("abs_diff_pp") is not None:
            st.caption(
                f"Headline contrast (top two pathways): "
                f"abs diff {hl['abs_diff_pp']:+} pp, RR {hl.get('rr')}, "
                f"Fisher p {hl.get('fishers_exact_p')}, E-value {hl.get('evalue_point')}"
            )
    if answer.get("factual_value"):
        fv = answer["factual_value"]
        st.markdown(
            f"<div style='margin-top:14px;padding:14px 16px;background:#f1f5f9;"
            f"border-radius:8px;font-size:14px;'><b>{fv.get('label')}:</b> "
            f"{fv.get('value')} patients.</div>",
            unsafe_allow_html=True,
        )


# =====================================================================
# Subgroup detail (per-stratifier panel with reliability badges + CMH)
# =====================================================================

def _reliability_chip(tag: str) -> str:
    c = _RELIABILITY_BADGE_COLOR.get(tag, "#94a3b8")
    return (f"<span style='display:inline-block;padding:1px 8px;font-size:10.5px;"
            f"font-weight:600;border-radius:6px;background:{c}15;color:{c};"
            f"border:1px solid {c}40;'>{tag}</span>")


def _render_subgroup_detail(answer: Dict[str, Any], st) -> None:
    sd = answer.get("subgroup_detail")
    if not sd: return
    st.markdown("<p class='section-label' style='margin-top:18px;'>Subgroup detail</p>",
                unsafe_allow_html=True)
    for sname, sblock in sd.items():
        title = sblock.get("stratifier_display", sname)
        cmh = sblock.get("cochran_mantel_haenszel")
        cmh_text = ""
        if cmh and cmh.get("mh_or") is not None:
            ci = cmh.get("mh_or_ci") or (None, None)
            cmh_text = (f" &nbsp;|&nbsp; <b>CMH pooled OR:</b> {cmh['mh_or']} "
                       f"({ci[0]}–{ci[1]}); p = {cmh.get('p_value')}")
        st.markdown(
            f"<div style='margin-top:10px;font-size:13px;font-weight:600;'>"
            f"Stratified by {title}{cmh_text}</div>",
            unsafe_allow_html=True,
        )
        rows = sblock.get("rows") or []
        if not rows:
            st.caption("No strata."); continue
        # build the dataframe
        arm_keys = [k for k in rows[0].keys() if k.startswith("arm_")]
        a_col = arm_keys[0].replace("arm_", "") if arm_keys else "Arm A"
        b_col = arm_keys[1].replace("arm_", "") if len(arm_keys) > 1 else "Arm B"
        df = pd.DataFrame([{
            "Stratum": r["stratum"],
            a_col: r.get(arm_keys[0], "-") if arm_keys else "-",
            b_col: r.get(arm_keys[1], "-") if len(arm_keys) > 1 else "-",
            "Difference": r.get("difference", "-"),
            "Reliability": r.get("reliability", "-"),
        } for r in rows])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(sblock.get("reliability_legend", ""))


# =====================================================================
# Interpretation
# =====================================================================

def _render_interpretation(answer: Dict[str, Any], st) -> None:
    interp = answer.get("interpretation")
    if not interp: return
    st.markdown("<p class='section-label' style='margin-top:18px;'>Interpretation</p>",
                unsafe_allow_html=True)
    st.markdown(
        f"<div style='padding:12px 16px;background:#fff7ed;border-left:3px solid "
        f"#f59e0b;border-radius:4px;font-size:13.5px;line-height:1.55;'>{interp}</div>",
        unsafe_allow_html=True,
    )


# =====================================================================
# Caveats (locked vs LLM)
# =====================================================================

def _render_caveats(answer: Dict[str, Any], st) -> None:
    cav = answer.get("caveats_and_limitations") or []
    if not cav: return
    st.markdown("<p class='section-label' style='margin-top:18px;'>Caveats and limitations</p>",
                unsafe_allow_html=True)
    for c in cav:
        label = c.get("label", "Caveat")
        body = c.get("body", "")
        anchor = c.get("anchor", "")
        locked = c.get("locked", False)
        marker = ("<span style='font-size:10.5px;font-weight:600;color:#0369a1;"
                  "background:#e0f2fe;padding:1px 7px;border-radius:5px;"
                  "margin-right:6px;'>LOCKED</span>" if locked
                  else "<span style='font-size:10.5px;font-weight:600;color:#7c3aed;"
                       "background:#f3e8ff;padding:1px 7px;border-radius:5px;"
                       "margin-right:6px;'>LLM</span>")
        st.markdown(
            f"<div style='margin-bottom:8px;padding:10px 12px;"
            f"background:#f8fafc;border-radius:6px;border:1px solid #e2e8f0;"
            f"font-size:12.5px;'>{marker}<b>{label}</b> "
            f"<span style='color:#64748b;font-size:11px;'>({anchor})</span>"
            f"<br><span style='color:#334155;'>{body}</span></div>",
            unsafe_allow_html=True,
        )


# =====================================================================
# Appendix: baseline differences + adjusted analysis
# =====================================================================

def _render_appendix(answer: Dict[str, Any], st) -> None:
    has_baseline = bool(answer.get("appendix_baseline_differences"))
    has_adjusted = bool(answer.get("appendix_adjusted_analysis"))
    if not (has_baseline or has_adjusted): return

    with st.expander("Appendix: baseline differences and adjusted analysis", expanded=False):
        if has_baseline:
            bd = answer["appendix_baseline_differences"]
            st.markdown(f"<p style='font-size:12px;color:#64748b;margin:0 0 6px 0;'>"
                       f"{bd.get('gloss', '')}</p>", unsafe_allow_html=True)
            rows = bd.get("rows") or []
            if rows:
                arm_keys = [k for k in rows[0] if k.startswith("arm_")]
                a_col = arm_keys[0].replace("arm_", "") if arm_keys else "Arm A"
                b_col = arm_keys[1].replace("arm_", "") if len(arm_keys) > 1 else "Arm B"
                df = pd.DataFrame([{
                    "Feature": r["feature"],
                    a_col: r.get(arm_keys[0], "-") if arm_keys else "-",
                    b_col: r.get(arm_keys[1], "-") if len(arm_keys) > 1 else "-",
                    "SMD": r.get("smd"),
                    "Imbalanced (SMD>0.10)": ("yes" if r.get("imbalanced") else "no"),
                } for r in rows])
                st.dataframe(df, use_container_width=True, hide_index=True)
        if has_adjusted:
            adj = answer["appendix_adjusted_analysis"]
            st.markdown("<p class='section-label' style='margin-top:14px;'>"
                       "Multi-covariate IPW</p>", unsafe_allow_html=True)
            st.markdown(f"<p style='font-size:12px;color:#64748b;margin:0 0 6px 0;'>"
                       f"{adj.get('gloss', '')}</p>", unsafe_allow_html=True)
            adjusters = adj.get("adjusters") or []
            st.write(f"**Method:** {adj.get('method')}  ·  **Adjusters:** {', '.join(adjusters)}")
            rr_ci = adj.get("adjusted_rr_ci") or (None, None)
            st.markdown(
                f"""<div style='padding:10px 14px;background:#f1f5f9;border-radius:6px;
                font-size:13px;'>
                <b>Unadjusted abs diff:</b> {adj.get('unadjusted_abs_diff_pp')} pp.
                &nbsp;&nbsp;<b>Adjusted abs diff:</b> {adj.get('adjusted_abs_diff_pp')} pp.
                &nbsp;&nbsp;<b>Adjusted RR:</b> {adj.get('adjusted_rr')} ({rr_ci[0]}–{rr_ci[1]}).
                &nbsp;&nbsp;<b>Gap (unadj − adj):</b> {adj.get('gap_pp')} pp.
                </div>""",
                unsafe_allow_html=True,
            )


# =====================================================================
# Debug toggle
# =====================================================================

def _render_debug(answer: Dict[str, Any], st) -> None:
    with st.expander("Debug: router plan, locked block, verifier", expanded=False):
        plan = answer.get("router_plan") or {}
        if plan:
            st.markdown("**Router plan**")
            st.json(plan)
        ng = answer.get("_numeric_grounding")
        if ng:
            ok = ng.get("ok"); miss = ng.get("missing_numbers", [])
            st.write(f"**Numeric grounding:** {'OK' if ok else 'mismatches found'}"
                    f" ({len(miss)} unverified numbers out of {ng.get('total_numbers', 0)})")
        er = answer.get("_entity_recall")
        if er:
            st.write(f"**Entity recall:** found {len(er.get('found', []))}, "
                    f"missing {er.get('missing', [])}")
        if answer.get("_responsivity_applied") is not None:
            st.write(f"**Responsivity pass applied:** {answer['_responsivity_applied']}")
        blk = answer.get("_locked_block")
        if blk:
            st.text_area("Locked analysis block", value=blk, height=300)


# =====================================================================
# Error / compound rendering
# =====================================================================

def _render_error(answer: Dict[str, Any], st) -> None:
    st.error(f"**{answer.get('error', 'error')}** — "
            f"{answer.get('failure_reason', 'unknown')}")
    if answer.get("router_plan"):
        with st.expander("Router plan (for debugging)"):
            st.json(answer["router_plan"])


def _render_compound(answer: Dict[str, Any], st) -> None:
    st.markdown(
        "<div style='padding:10px 14px;background:#eff6ff;border-radius:6px;"
        "font-size:13.5px;color:#1e3a5f;'>"
        "<b>Compound question.</b> Sub-answers below address each part separately."
        "</div>", unsafe_allow_html=True)
    for i, sub in enumerate(answer.get("sub_answers", []), 1):
        st.markdown(f"<p class='section-label' style='margin-top:20px;'>Part {i}</p>",
                    unsafe_allow_html=True)
        render_answer(sub, st)
