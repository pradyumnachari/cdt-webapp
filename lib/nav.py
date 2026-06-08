"""Top-of-page navigation bar shared across pages."""

import streamlit as st

# Order: overview -> try -> recommendation -> cohort
_NAV_ITEMS = [
    ("overview",       "Overview",       "app.py"),
    ("try",            "Try it",         "pages/1_Try_it.py"),
    ("recommendation", "Recommendation", "pages/2_Recommendation.py"),
    ("cohort",         "Cohort",         "pages/3_Cohort.py"),
]

# Inline logo: a root node branching to three coloured action leaves
# (green = watch & wait, blue = surgery, red = radiation).
_LOGO_SVG = """
<svg width="34" height="32" viewBox="0 0 34 32" fill="none"
     xmlns="http://www.w3.org/2000/svg" aria-label="CDT logo"
     style="display:block;">
  <path d="M17 7 L7 23" stroke="#94a3b8" stroke-width="1.5"
        stroke-linecap="round"/>
  <path d="M17 7 L17 23" stroke="#94a3b8" stroke-width="1.5"
        stroke-linecap="round"/>
  <path d="M17 7 L27 23" stroke="#94a3b8" stroke-width="1.5"
        stroke-linecap="round"/>
  <circle cx="17" cy="6" r="4" fill="#1e3a8a"/>
  <circle cx="7"  cy="25" r="3.5" fill="#16a34a"/>
  <circle cx="17" cy="25" r="3.5" fill="#2563eb"/>
  <circle cx="27" cy="25" r="3.5" fill="#dc2626"/>
</svg>
"""


def render(active: str) -> None:
    """Render a clean horizontal nav row at the top of each page."""
    cols = st.columns([3.0, 1.15, 1.05, 1.35, 1.15])

    with cols[0]:
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:11px;
                        padding-top:2px;">
                <div>{_LOGO_SVG}</div>
                <div style="line-height:1.15;">
                    <div style="font-size:15px;font-weight:700;
                                letter-spacing:-0.015em;color:#0f172a;">
                        Clinical&nbsp;Decision&nbsp;Tree
                    </div>
                    <div style="font-size:11px;font-weight:500;
                                color:#64748b;letter-spacing:0.02em;
                                margin-top:1px;">
                        meningioma · real-data recommender
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for col, (key, label, page_path) in zip(cols[1:], _NAV_ITEMS):
        with col:
            label_display = f"**{label}**" if active == key else label
            if st.button(label_display, key=f"nav_{key}",
                         use_container_width=True):
                if active != key:
                    st.switch_page(page_path)

    st.markdown(
        "<div style='border-bottom:1px solid #e2e8f0;margin:6px 0 14px 0;'></div>",
        unsafe_allow_html=True,
    )
