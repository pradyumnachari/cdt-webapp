"""Top-of-page navigation bar shared across all pages."""

from __future__ import annotations

import streamlit as st

from . import style

_NAV_ITEMS = [
        ("overview", "Overview",              "app.py"),
        ("ask",      "Ask my data",           "pages/1_Ask_my_data.py"),
        ("viz",      "Visualize",             "pages/2_Visualizations.py"),
        ("similar",  "Find similar patients", "pages/3_Similar_patients_and_evidence.py"),
]


def render(active: str) -> None:
        pills = ""
        for key, label, _ in _NAV_ITEMS:
                    cls = "nav-pill active" if active == key else "nav-pill"
                    pills += f'<span class="{cls}">{label}</span>'

        st.markdown(
            f"""
            <div class="topbar">
                <span class="topbar-brand">ask my data</span>
                <div class="topbar-nav">{pills}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    style.banner()

    # Hidden functional buttons for Streamlit routing
    st.markdown("<div style='height:0;overflow:hidden;position:absolute;'>", unsafe_allow_html=True)
    cols = st.columns(len(_NAV_ITEMS))
    for col, (key, label, page_path) in zip(cols, _NAV_ITEMS):
                with col:
                                if st.button(label, key=f"nav_{key}"):
                                                    if active != key:
                                                                            st.switch_page(page_path)
                                                            st.markdown("</div>", unsafe_allow_html=True)
