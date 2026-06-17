"""Top-of-page navigation bar shared across pages.

Renders a horizontal nav with four destinations (Overview, Ask my data,
Visualizations, Similar patients & evidence) and a persistent experimental
banner below the strip. The banner appears on every page automatically.
"""

import streamlit as st

from . import style

# Page order matches Streamlit's numeric-prefix ordering on disk.
_NAV_ITEMS = [
    ("overview", "Overview",            "app.py"),
    ("ask",      "Ask My Data",         "pages/1_Ask_my_data.py"),
    ("viz",      "Visualizations",      "pages/2_Visualizations.py"),
    ("similar",  "Similar Patients",    "pages/3_Similar_patients.py"),
    ("tech",     "Technical Details",   "pages/4_Technical_details.py"),
]

# Inline logo: a root node branching to three coloured action leaves
# (green = watch & wait, blue = surgery, red = radiation).
_LOGO_SVG = """
<svg width="34" height="32" viewBox="0 0 34 32" fill="none"
     xmlns="http://www.w3.org/2000/svg" aria-label="Ask my data logo"
     style="display:block;">
  <path d="M17 7 L7 23" stroke="#64748b" stroke-width="1.5"
        stroke-linecap="round"/>
  <path d="M17 7 L17 23" stroke="#64748b" stroke-width="1.5"
        stroke-linecap="round"/>
  <path d="M17 7 L27 23" stroke="#64748b" stroke-width="1.5"
        stroke-linecap="round"/>
  <circle cx="17" cy="6" r="4" fill="#1e3a8a"/>
  <circle cx="7"  cy="25" r="3.5" fill="#16a34a"/>
  <circle cx="17" cy="25" r="3.5" fill="#2563eb"/>
  <circle cx="27" cy="25" r="3.5" fill="#dc2626"/>
</svg>
"""


def render(active: str) -> None:
    """Render the horizontal nav row + the persistent experimental banner.

    The column ratios privilege the logo cell, then give each of the four
    tabs comparable width (the "Similar patients & evidence" label is the
    longest, so its column is slightly wider). On narrow viewports the
    responsive CSS in style.py wraps the cells to a 2-up or 1-up grid.
    """
    # 5 columns: logo + 4 tabs. The "Similar patients & evidence" cell
    # gets extra width because the label is longest.
    cols = st.columns([2.8, 1.0, 1.1, 1.2, 1.4, 1.4])

    with cols[0]:
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:11px;
                        padding-top:2px;">
                <div>{_LOGO_SVG}</div>
                <div style="line-height:1.15;">
                    <div style="font-size:15px;font-weight:700;
                                letter-spacing:-0.015em;color:#0f172a;">
                        Ask&nbsp;my&nbsp;data
                    </div>
                    <div style="font-size:11.5px;font-weight:500;
                                color:#475569;letter-spacing:0.02em;
                                margin-top:1px;">
                        meningioma cohort · retrospective explorer
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

    # Thin separator under the nav row, then the persistent banner.
    st.markdown(
        "<div style='border-bottom:1px solid #e2e8f0;margin:6px 0 0 0;'></div>",
        unsafe_allow_html=True,
    )
    style.banner()
