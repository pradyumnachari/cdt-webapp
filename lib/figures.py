"""
Cohort pathway visualisations — self-contained Sankey builders.

Ported from cdt_webapp_v2/lib/figures.py and adapted to the v3 record
schema (`levels` instead of `level_info`, `outcome` instead of `outcomes`).
Same logic, same look.

  * build_action_outcome_sankey  — Level-1 State -> Treatment -> Outcome
  * build_trajectory_sankey      — L1 action -> L2 action -> Outcome
"""

from __future__ import annotations

from collections import defaultdict
from typing import List, Optional

import plotly.graph_objects as go

from .buckets import ACTION_COLORS, ACTION_LABELS, OUTCOME_COLORS


# ── small utilities ────────────────────────────────────────────────────────
def _hex_to_rgba(hex_color: str, alpha: float = 0.6) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"
    return hex_color


def _func(p: dict) -> str:
    return p.get("outcome", {}).get("functional_status", "unknown")


def _action_seq(p: dict) -> List[str]:
    levels = p.get("levels", {})
    return [levels[lv]["action"] for lv in sorted(levels)]


# ── Sankey #1: State → Action → Outcome ────────────────────────────────────
def build_action_outcome_sankey(patients: List[dict]) -> Optional[go.Figure]:
    """Sankey: Level-1 State -> Level-1 Action -> Outcome."""
    state_action_outcome = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    for p in patients:
        li1 = p.get("levels", {}).get(1, {})
        state = li1.get("state_key", "unknown")
        action = li1.get("action", "unknown")
        state_action_outcome[state][action][_func(p)] += 1

    nodes: list = []
    node_idx: dict = {}

    def _get_node(label: str, color: str = "#94a3b8") -> int:
        if label not in node_idx:
            node_idx[label] = len(nodes)
            nodes.append({"label": label, "color": color})
        return node_idx[label]

    state_colors = ["#1e3a8a", "#2563eb", "#3b82f6", "#60a5fa", "#93c5fd"]
    sources, targets, values, link_colors = [], [], [], []

    for i, state in enumerate(sorted(state_action_outcome.keys())):
        sc = state_colors[i % len(state_colors)]
        s_idx = _get_node(state.replace("_", " "), sc)
        for action, outcomes in state_action_outcome[state].items():
            act_color = ACTION_COLORS.get(action, "#94a3b8")
            a_label = ACTION_LABELS.get(action, action)
            a_idx = _get_node(f"{a_label} [{state.replace('_', ' ')}]",
                              act_color)
            sources.append(s_idx)
            targets.append(a_idx)
            values.append(sum(outcomes.values()))
            link_colors.append(_hex_to_rgba(act_color, 0.5))

            for outcome, cnt in outcomes.items():
                oc = OUTCOME_COLORS.get(outcome, "#94a3b8")
                o_idx = _get_node(
                    f"{outcome.title()} [{a_label}·{state[:4]}]", oc)
                sources.append(a_idx)
                targets.append(o_idx)
                values.append(cnt)
                link_colors.append(_hex_to_rgba(oc, 0.45))

    if not sources:
        return None

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=18, thickness=16,
            label=[n["label"].split("[")[0].strip() for n in nodes],
            color=[n["color"] for n in nodes],
            line=dict(width=0),
            hovertemplate="%{label}<br>n = %{value}<extra></extra>",
        ),
        link=dict(source=sources, target=targets, value=values,
                  color=link_colors),
    ))
    fig.update_layout(
        title=dict(text="<b>State → Treatment → Outcome</b>",
                   font=dict(size=13, color="#0f172a")),
        height=460, margin=dict(t=44, b=8, l=8, r=8),
        font=dict(size=11.5, color="#0f172a"), paper_bgcolor="white",
    )
    return fig


# ── Sankey #2: L1 → L2 → Outcome (pathway) ─────────────────────────────────
def build_trajectory_sankey(patients: List[dict]) -> Optional[go.Figure]:
    """
    Sankey: L1 Action -> L2 Action (or 'end') -> Outcome.

    The NCCN-adjacent surgery -> radiation pathway is highlighted in red.
    """
    nccn_color = "#dc2626"

    l1_l2_outcome = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for p in patients:
        seq = _action_seq(p)
        l1 = seq[0] if len(seq) > 0 else "unknown"
        l2 = seq[1] if len(seq) > 1 else "— end —"
        l1_l2_outcome[l1][l2][_func(p)] += 1

    nodes: list = []
    node_idx: dict = {}

    def _get_node(label: str, color: str = "#94a3b8") -> int:
        if label not in node_idx:
            node_idx[label] = len(nodes)
            nodes.append({"label": label, "color": color})
        return node_idx[label]

    sources, targets, values, link_colors = [], [], [], []

    for l1, l2_dict in sorted(l1_l2_outcome.items()):
        l1_color = ACTION_COLORS.get(l1, "#94a3b8")
        l1_idx = _get_node(f"L1: {ACTION_LABELS.get(l1, l1)}", l1_color)

        for l2, outcomes in l2_dict.items():
            if l2 == "— end —":
                l2_color, l2_label = "#cbd5e1", "— end —"
            else:
                l2_color = ACTION_COLORS.get(l2, "#94a3b8")
                l2_label = f"L2: {ACTION_LABELS.get(l2, l2)}"
            is_nccn = (l1 == "surgery" and l2 == "radiation")
            l2_idx = _get_node(f"{l2_label} [after {l1}]",
                               nccn_color if is_nccn else l2_color)

            sources.append(l1_idx)
            targets.append(l2_idx)
            values.append(sum(outcomes.values()))
            link_colors.append(
                _hex_to_rgba(nccn_color, 0.55) if is_nccn
                else _hex_to_rgba(l2_color, 0.45))

            for outcome, cnt in outcomes.items():
                oc = OUTCOME_COLORS.get(outcome, "#94a3b8")
                o_idx = _get_node(
                    f"{outcome.title()} [{l2_label[:4]}·{l1[:3]}]", oc)
                sources.append(l2_idx)
                targets.append(o_idx)
                values.append(cnt)
                link_colors.append(_hex_to_rgba(oc, 0.45))

    if not sources:
        return None

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=18, thickness=16,
            label=[n["label"].split("[")[0].strip() for n in nodes],
            color=[n["color"] for n in nodes],
            line=dict(width=0),
            hovertemplate="%{label}<br>n = %{value}<extra></extra>",
        ),
        link=dict(source=sources, target=targets, value=values,
                  color=link_colors),
    ))
    fig.update_layout(
        title=dict(
            text="<b>L1 → L2 → Outcome</b>  "
                 "<span style='color:#dc2626;font-size:11px;'>"
                 "(red = NCCN-adjacent: surgery → radiation)</span>",
            font=dict(size=13, color="#0f172a")),
        height=460, margin=dict(t=44, b=8, l=8, r=8),
        font=dict(size=11.5, color="#0f172a"), paper_bgcolor="white",
    )
    return fig
