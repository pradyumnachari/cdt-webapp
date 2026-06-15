"""Visualizations — descriptive cohort statistics and treatment-flow diagrams."""

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
from lib.buckets import ACTION_COLORS, ACTION_LABELS, OUTCOME_COLORS  # noqa: E402
from lib.engine import cohort_stats  # noqa: E402
from lib.figures import build_action_outcome_sankey  # noqa: E402

st.set_page_config(page_title="Visualize — Ask my data", page_icon="🧠",
                                      layout="wide", initial_sidebar_state="collapsed")
style.inject()
nav.render("viz")

# ── Hero ───────────────────────────────────────────────────────────────────

st.markdown(
      """
          <div class="hero">
                  <p class="hero-eyebrow">Visualize</p>
                          <h1 class="hero-title-inner">
                                      Who is in this cohort, how did they do,<br/>and how did they get there?
                                              </h1>
                                                      <p class="hero-sub-inner">
                                                                  Filter the cohort by grade, location, age, or sex — the page
                                                                              recomputes live. Hover any bar or ribbon to see exact counts.
                                                                                      </p>
                                                                                          </div>
                                                                                              """,
      unsafe_allow_html=True,
)

cohort   = get_cohort()
patients = cohort["patients"]

# ── Label maps ─────────────────────────────────────────────────────────────

_GRADE_LABEL  = {"grade_1": "WHO grade 1", "grade_2": "WHO grade 2", "grade_3": "WHO grade 3"}
_LOC_LABEL    = {"skull_base": "Skull base", "convexity": "Convexity",
                                  "parasagittal": "Parasagittal", "sphenoid_wing": "Sphenoid wing", "other": "Other"}
_AGE_LABEL    = {"<50": "Under 50", "50-65": "50–65", ">=65": "65 or older"}
_GENDER_LABEL = {"M": "Male", "F": "Female"}

def _disp(value: str, mapping: dict) -> str:
      return mapping.get(value, str(value).replace("_", " "))

# ── Sankey styling ─────────────────────────────────────────────────────────

NODE_PALETTE = {
      "watch_and_wait": "#bbf7d0",
      "surgery":        "#ddd6fe",
      "radiation":      "#fecaca",
      "functional":     "#a5f3fc",
      "impaired":       "#fed7aa",
      "ended":          "#1e293b",
      "fallback":       "#1e293b",
}

_READABLE_TEXTFONT = dict(color="#f1f5f9", size=13,
                                                     family="Inter, system-ui, sans-serif")

def _node_color_for(label: str) -> str:
      lo = (label or "").lower()
      if "ended after" in lo: return NODE_PALETTE["ended"]
            if "watch" in lo:       return NODE_PALETTE["watch_and_wait"]
                  if "surgery" in lo:     return NODE_PALETTE["surgery"]
                        if "radiation" in lo:   return NODE_PALETTE["radiation"]
                              if "functional" in lo:  return NODE_PALETTE["functional"]
                                    if "impaired" in lo:    return NODE_PALETTE["impaired"]
                                          return NODE_PALETTE["fallback"]

def _readable_sankey(fig):
      if fig is None: return fig
            try:
                      node, link = fig.data[0].node, fig.data[0].link
                      labels = list(node.label or [])
                      node_colors = [_node_color_for(lbl) for lbl in labels]
                      node.color = node_colors

        def _rgba(h: str, a: float = 0.6) -> str:
                      h = h.lstrip("#")
                      if len(h) != 6: return h
                                    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            return f"rgba({r},{g},{b},{a})"

        targets = list(link.target or [])
        link.color = [_rgba(node_colors[t]) if 0 <= t < len(node_colors) else _rgba("#1e293b") for t in targets]

        fig.update_traces(textfont=_READABLE_TEXTFONT)
        fig.update_layout(paper_bgcolor="#050505", plot_bgcolor="#050505",
                                                    font=dict(color="#f1f5f9"))
except Exception: pass
    return fig

# ── Filters ────────────────────────────────────────────────────────────────

def _unique_values(path: tuple) -> list:
      vals = set()
    for r in patients.values():
              d = r
        for k in path: d = d[k]
                  vals.add(d)
    return sorted(str(v) for v in vals)

def _on_reset():
      for k in ("flt_grade", "flt_loc", "flt_age", "flt_gender"):
                st.session_state.pop(k, None)
    st.rerun()

st.markdown("<p class='section-label'>Filter the cohort</p>", unsafe_allow_html=True)

f1, f2, f3, f4 = st.columns(4)
with f1:
      grade_sel = st.multiselect("WHO grade", options=_unique_values(("stratification","grade")),
                                                                format_func=lambda v: _disp(v, _GRADE_LABEL), key="flt_grade", placeholder="All grades")
with f2:
      loc_sel = st.multiselect("Tumour location", options=_unique_values(("stratification","location")),
                                                            format_func=lambda v: _disp(v, _LOC_LABEL), key="flt_loc", placeholder="All locations")
with f3:
      age_sel = st.multiselect("Age band", options=_unique_values(("stratification","age")),
                                                            format_func=lambda v: _disp(v, _AGE_LABEL), key="flt_age", placeholder="All ages")
with f4:
      gender_sel = st.multiselect("Sex", options=_unique_values(("stratification","gender")),
                                                                  format_func=lambda v: _disp(v, _GENDER_LABEL), key="flt_gender", placeholder="All")

reset_col, _ = st.columns([1, 6])
with reset_col:
      st.button("Reset filters", on_click=_on_reset, type="secondary", use_container_width=True)

def _keep(r: dict) -> bool:
      s = r["stratification"]
    return ((not grade_sel  or s["grade"]    in grade_sel)
                    and (not loc_sel    or s["location"] in loc_sel)
                    and (not age_sel    or s["age"]      in age_sel)
                    and (not gender_sel or s["gender"]   in gender_sel))

filtered = {p: r for p, r in patients.items() if _keep(r)}
n_total, n_filt = len(patients), len(filtered)
frac = (n_filt / n_total * 100) if n_total else 0

st.markdown(
      f"<div class='info-line' style='margin-top:6px;font-size:13px;'>"
      f"Showing <b style='color:#f1f5f9;'>{n_filt:,}</b> of <b style='color:#f1f5f9;'>{n_total:,}</b> patients "
      f"({frac:.0f}% of cohort).</div>",
      unsafe_allow_html=True,
)

if not filtered:
      st.warning("No patients match the current filters. Use Reset filters above.")
    style.footer()
    st.stop()

# ── Cohort at a glance ─────────────────────────────────────────────────────

st.markdown("<p class='section-label'>Cohort at a glance</p>", unsafe_allow_html=True)

stats    = cohort_stats(filtered)
baseline = cohort_stats(patients)
n_known  = stats["n_outcome_known"]
n_func   = stats["n_functional"]
n_imp    = n_known - n_func
n_unknown = stats["n"] - n_known
rate     = stats["functional_rate"]
ci_lo, ci_hi = qa.clopper_pearson(n_func, n_known) if n_known else (0, 0)
baseline_rate = baseline["functional_rate"]
is_filtered   = (n_filt != n_total)

def _seg(label, n, total, color):
      if total <= 0 or n <= 0: return ""
            pct = n / total * 100
    return (f"<div style='flex:{n};background:{color};height:12px;"
                        f"display:flex;align-items:center;justify-content:center;"
                        f"font-size:10px;color:white;font-weight:700;'"
                        f"title='{label}: {n} ({pct:.0f}%)'></div>")

bar_total = max(stats["n"], 1)
composition_bar = (
      "<div style='display:flex;width:100%;border-radius:4px;overflow:hidden;"
      "border:1px solid #1e293b;margin-top:8px;'>"
      + _seg("Functional", n_func, bar_total, "#16a34a")
      + _seg("Impaired",   n_imp,  bar_total, "#ea580c")
      + _seg("Unknown",    n_unknown, bar_total, "#334155")
      + "</div>"
      + "<div style='display:flex;gap:14px;margin-top:8px;font-size:12px;color:#64748b;'>"
      + f"<span><span style='display:inline-block;width:9px;height:9px;background:#16a34a;border-radius:2px;margin-right:4px;'></span>Functional ({n_func})</span>"
      + f"<span><span style='display:inline-block;width:9px;height:9px;background:#ea580c;border-radius:2px;margin-right:4px;'></span>Impaired ({n_imp})</span>"
      + (f"<span><span style='display:inline-block;width:9px;height:9px;background:#334155;border-radius:2px;margin-right:4px;'></span>Unknown ({n_unknown})</span>" if n_unknown else "")
      + "</div>"
)

block_l, block_r = st.columns([1.1, 1])

with block_l:
      st.markdown(
          f"<div class='stat-card' style='padding:16px 18px;'>"
          f"<p class='stat-card-label'>Patients in selection</p>"
          f"<p class='stat-card-value' style='font-size:1.8rem;'>{stats['n']:,}</p>"
          f"{composition_bar}</div>",
          unsafe_allow_html=True,
)

with block_r:
      if rate is not None:
                rate_pct = f"{rate * 100:.1f}%"
                ci_str = f"95% CI: {ci_lo*100:.1f}% – {ci_hi*100:.1f}%" if n_known else ""
                if is_filtered and baseline_rate is not None:
                              delta = (rate - baseline_rate) * 100
                              arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "—")
                              arrow_color = "#4ade80" if delta > 0 else ("#f87171" if delta < 0 else "#64748b")
                              baseline_line = (
                                  f"<div style='font-size:12px;color:#475569;margin-top:6px;'>"
                                  f"vs. {baseline_rate*100:.1f}% in full cohort "
                                  f"<span style='color:{arrow_color};font-weight:600;'>{arrow} {abs(delta):.1f} pp</span></div>"
                              )
else:
            baseline_line = "<div style='font-size:12px;color:#475569;margin-top:6px;'>Full cohort.</div>"
else:
        rate_pct, ci_str, baseline_line = "—", "no patients with a recorded outcome", ""

    st.markdown(
              f"<div class='stat-card' style='padding:16px 18px;'>"
              f"<p class='stat-card-label'>Functional at last follow-up "
              f"<span title='Functional = ECOG 0–2 or KPS ≥ 70 at last recorded follow-up. "
              f"Impaired = ECOG 3–4 or KPS &lt; 70.' "
              f"style='cursor:help;color:#3b82f6;font-size:12px;'>ⓘ</span></p>"
              f"<p class='stat-card-value' style='font-size:1.8rem;'>{rate_pct}</p>"
              f"<div style='font-size:12px;color:#475569;'>{ci_str}</div>"
              f"{baseline_line}</div>",
              unsafe_allow_html=True,
    )

# ── Decision levels explainer ──────────────────────────────────────────────

st.markdown("<p class='section-label'>Decision levels: L1 · L2 · L3</p>", unsafe_allow_html=True)

st.markdown(
      """
          <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px;'>
                  <div style='border:1px solid #1e293b;border-left:3px solid #3b82f6;
                                      border-radius:0 8px 8px 0;padding:12px 14px;background:#0a0f1a;'>
                                                  <div style='font-size:11px;font-weight:700;text-transform:uppercase;
                                                                          letter-spacing:0.1em;color:#3b82f6;margin-bottom:4px;'>L1 — First decision</div>
                                                                                      <div style='font-size:12.5px;color:#64748b;line-height:1.5;'>
                                                                                                      The first treatment choice after diagnosis.
                                                                                                                  </div>
                                                                                                                          </div>
                                                                                                                                  <div style='border:1px solid #1e293b;border-left:3px solid #8b5cf6;
                                                                                                                                                      border-radius:0 8px 8px 0;padding:12px 14px;background:#0a0f1a;'>
                                                                                                                                                                  <div style='font-size:11px;font-weight:700;text-transform:uppercase;
                                                                                                                                                                                          letter-spacing:0.1em;color:#8b5cf6;margin-bottom:4px;'>L2 — Next decision</div>
                                                                                                                                                                                                      <div style='font-size:12.5px;color:#64748b;line-height:1.5;'>
                                                                                                                                                                                                                      Triggered by recurrence, growth, or new symptoms.
                                                                                                                                                                                                                                  </div>
                                                                                                                                                                                                                                          </div>
                                                                                                                                                                                                                                                  <div style='border:1px solid #1e293b;border-left:3px solid #ec4899;
                                                                                                                                                                                                                                                                      border-radius:0 8px 8px 0;padding:12px 14px;background:#0a0f1a;'>
                                                                                                                                                                                                                                                                                  <div style='font-size:11px;font-weight:700;text-transform:uppercase;
                                                                                                                                                                                                                                                                                                          letter-spacing:0.1em;color:#ec4899;margin-bottom:4px;'>L3 — Third decision</div>
                                                                                                                                                                                                                                                                                                                      <div style='font-size:12.5px;color:#64748b;line-height:1.5;'>
                                                                                                                                                                                                                                                                                                                                      Reached by fewer patients. Many never get here.
                                                                                                                                                                                                                                                                                                                                                  </div>
                                                                                                                                                                                                                                                                                                                                                          </div>
                                                                                                                                                                                                                                                                                                                                                              </div>
                                                                                                                                                                                                                                                                                                                                                                  <div class='info-line' style='font-size:12.5px;'>
                                                                                                                                                                                                                                                                                                                                                                          Consecutive same-action events (e.g. years of stable surveillance) are collapsed into one level.
                                                                                                                                                                                                                                                                                                                                                                                  Actions: <span style='background:#052e16;color:#4ade80;padding:1px 8px;border-radius:4px;font-weight:600;'>Watch &amp; Wait</span>
                                                                                                                                                                                                                                                                                                                                                                                          &nbsp;<span style='background:#0d1526;color:#93c5fd;padding:1px 8px;border-radius:4px;font-weight:600;'>Surgery</span>
                                                                                                                                                                                                                                                                                                                                                                                                  &nbsp;<span style='background:#1f0a0a;color:#fca5a5;padding:1px 8px;border-radius:4px;font-weight:600;'>Radiation</span>
                                                                                                                                                                                                                                                                                                                                                                                                      </div>
                                                                                                                                                                                                                                                                                                                                                                                                          """,
      unsafe_allow_html=True,
)

# ── Treatment pathways ─────────────────────────────────────────────────────

st.markdown("<p class='section-label'>Treatment pathways</p>", unsafe_allow_html=True)

def _swatch(color: str, label: str) -> str:
      return (f"<span style='display:inline-flex;align-items:center;margin-right:16px;'>"
                          f"<span style='display:inline-block;width:12px;height:12px;background:{color};"
                          f"border:1px solid #334155;border-radius:2px;margin-right:6px;'></span>"
                          f"<span style='color:#64748b;font-size:12.5px;'>{label}</span></span>")

st.markdown(
      f"<div style='display:flex;flex-wrap:wrap;gap:4px 0;margin-bottom:12px;'>"
      + _swatch(NODE_PALETTE["watch_and_wait"], "Watch &amp; wait")
      + _swatch(NODE_PALETTE["surgery"],        "Surgery")
      + _swatch(NODE_PALETTE["radiation"],      "Radiation")
      + _swatch(NODE_PALETTE["functional"],     "Functional outcome")
      + _swatch(NODE_PALETTE["impaired"],       "Impaired outcome")
      + _swatch(NODE_PALETTE["ended"],          "Ended (no further treatment)")
      + "</div>",
      unsafe_allow_html=True,
)

recs = list(filtered.values())

def _action_seq(p): return [p["levels"][lv]["action"] for lv in sorted(p.get("levels", {}))]
  def _func(p): return p.get("outcome", {}).get("functional_status", "unknown")

def _hex_to_rgba(h, a=0.55):
      h = h.lstrip("#")
    if len(h)==6:
              r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
              return f"rgba({r},{g},{b},{a})"
          return h

def build_l1_l2_l3_sankey(records):
      paths = defaultdict(int)
    for p in records:
              seq = _action_seq(p)
              out = _func(p)
              if not seq: continue
                        l1 = seq[0]
        l2 = seq[1] if len(seq) > 1 else "ended after L1"
        l3 = (seq[2] if len(seq) > 2 else ("ended after L2" if len(seq) > 1 else "ended after L1"))
        paths[(l1, l2, l3, out)] += 1

    if not paths: return None

    nodes, node_idx = [], {}
    def _node(label, color):
              if label not in node_idx:
                            node_idx[label] = len(nodes)
                            nodes.append({"label": label, "color": color})
                        return node_idx[label]

    def _label_for(action, level):
              if action.startswith("ended after"): return action
                        return f"L{level}: {ACTION_LABELS.get(action, action)}"

    def _color_for(action):
              if action.startswith("ended after"): return "#1e293b"
                        return ACTION_COLORS.get(action, "#334155")

    sources, targets, values, link_colors = [], [], [], []
    l1_to_l2 = defaultdict(int); l2_to_l3 = defaultdict(int); l3_to_out = defaultdict(int)

    for (l1,l2,l3,out),c in paths.items():
              l1_to_l2[(l1,l2)]+=c; l2_to_l3[(l1,l2,l3)]+=c; l3_to_out[(l1,l2,l3,out)]+=c

    for (l1,l2),c in l1_to_l2.items():
              a=_node(f"{_label_for(l1,1)}__L1", _color_for(l1))
        b=_node(f"{_label_for(l2,2)}__L2_{l1}", _color_for(l2))
        sources.append(a);targets.append(b);values.append(c);link_colors.append(_hex_to_rgba(_color_for(l2)))

    for (l1,l2,l3),c in l2_to_l3.items():
              b=_node(f"{_label_for(l2,2)}__L2_{l1}", _color_for(l2))
        e=_node(f"{_label_for(l3,3)}__L3_{l1}_{l2}", _color_for(l3))
        sources.append(b);targets.append(e);values.append(c);link_colors.append(_hex_to_rgba(_color_for(l3)))

    for (l1,l2,l3,out),c in l3_to_out.items():
              e=_node(f"{_label_for(l3,3)}__L3_{l1}_{l2}", _color_for(l3))
        o=_node(f"{out.title()}__out_{l1}_{l2}_{l3}", OUTCOME_COLORS.get(out,"#334155"))
        sources.append(e);targets.append(o);values.append(c);link_colors.append(_hex_to_rgba(OUTCOME_COLORS.get(out,"#334155")))

    if not sources: return None

    display_labels = [n["label"].split("__")[0] for n in nodes]
    fig = go.Figure(go.Sankey(
              arrangement="snap",
              node=dict(pad=20, thickness=18, label=display_labels,
                                          color=[n["color"] for n in nodes],
                                          line=dict(width=0),
                                          hovertemplate="%{label}<br>n = %{value}<extra></extra>"),
              link=dict(source=sources, target=targets, value=values, color=link_colors),
    ))
    fig.update_layout(
              title=dict(text="<b>Full trajectory: L1 → L2 → L3 → Outcome</b>", font=dict(size=13, color="#f1f5f9")),
              height=560, margin=dict(t=44, b=10, l=10, r=10),
              font=dict(size=11.5, color="#f1f5f9"), paper_bgcolor="#050505",
    )
    return fig

def build_top_trajectories_table(records, top_n=12):
      counter: Counter = Counter()
    out_by_traj = defaultdict(lambda: {"functional":0,"impaired":0,"unknown":0})
    n_total = 0
    for p in records:
              seq = _action_seq(p)
        if not seq: continue
                  traj = " → ".join(f"L{i+1}: {ACTION_LABELS.get(a,a)}" for i,a in enumerate(seq))
        counter[traj] += 1
        out_by_traj[traj][_func(p)] += 1
        n_total += 1

    if not counter: return None

    rows = []
    for traj, n in counter.most_common(top_n):
              nf = out_by_traj[traj]["functional"]
        ni = out_by_traj[traj]["impaired"]
        nk = nf + ni
        rate = (nf/nk) if nk else None
        rows.append({"Trajectory": traj, "N": n,
                                          "% of cohort": f"{(n/n_total*100):.1f}%",
                                          "Functional rate": (f"{rate*100:.1f}%" if rate is not None else "—")})

    return {"rows": rows, "n_total": n_total, "n_unique": len(counter)}

tab1, tab2, tab3 = st.tabs([
      "Initial state → L1 treatment → outcome",
      "Full trajectory (L1 → L2 → L3 → outcome)",
      "Top trajectories ranked",
])

with tab1:
      st.markdown(
                "<div style='font-size:13px;color:#475569;margin-bottom:8px;'>"
                "Shows how a patient's clinical state at presentation connected to their first treatment "
                "decision (L1) and their eventual functional outcome. Thicker ribbons = more patients.</div>",
                unsafe_allow_html=True,
      )
    fig1 = _readable_sankey(build_action_outcome_sankey(recs))
    if fig1 is not None: st.plotly_chart(fig1, use_container_width=True)
else: st.caption("No pathway data for this filter.")

with tab2:
      st.markdown(
                "<div style='font-size:13px;color:#475569;margin-bottom:8px;'>"
                "The complete sequence of decisions: L1 (first treatment), L2 (next decision), "
                "L3 (third decision if reached), and final functional outcome. "
                "'Ended after L<i>n</i>' means no further decision was recorded.</div>",
                unsafe_allow_html=True,
      )
    fig2 = _readable_sankey(build_l1_l2_l3_sankey(recs))
    if fig2 is not None: st.plotly_chart(fig2, use_container_width=True)
else: st.caption("No pathway data for this filter.")

with tab3:
      st.markdown(
                "<div style='font-size:13px;color:#475569;margin-bottom:8px;'>"
                "Most common end-to-end treatment trajectories ranked by frequency. "
                "Functional rate is computed only over patients with a known outcome. "
                "Treatment levels are standardized as L1, L2, L3.</div>",
                unsafe_allow_html=True,
      )
    tt = build_top_trajectories_table(recs, top_n=12)
    if tt is None:
              st.caption("No pathway data for this filter.")
else:
        import pandas as pd
        df = pd.DataFrame(tt["rows"])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"{tt['n_unique']} unique trajectories across {tt['n_total']:,} patients; top 12 shown.")

style.footer()
