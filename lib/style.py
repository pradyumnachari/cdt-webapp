"""Global stylesheet + small UI helpers. One source of truth for all pages."""

from __future__ import annotations

import streamlit as st


_CSS = """
<style>
/* ── Reset Streamlit chrome ─────────────────────────────────────── */
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.6rem; max-width: 1180px; }

/* ── Type ───────────────────────────────────────────────────────── */
html, body, [class*="css"]  {
    font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI",
                 Roboto, Helvetica, Arial, sans-serif;
    color: #0f172a;
}
h1, h2, h3, h4 { letter-spacing: -0.015em; }

/* ── Hero ───────────────────────────────────────────────────────── */
.hero {
    padding: 36px 4px 18px 4px;
    border-bottom: 1px solid #e2e8f0;
    margin-bottom: 26px;
}
.hero-eyebrow {
    font-size: 11.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #2563eb;
    margin: 0 0 10px 0;
}
.hero-title {
    font-size: 2.15rem;
    font-weight: 700;
    margin: 0 0 12px 0;
    line-height: 1.15;
    color: #0f172a;
}
.hero-sub {
    font-size: 1.05rem;
    color: #475569;
    line-height: 1.55;
    margin: 0;
    max-width: 720px;
}

/* ── Exemplar tiles ─────────────────────────────────────────────── */
.tile {
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 18px 18px 16px 18px;
    background: #ffffff;
    transition: all 0.15s ease;
    height: 100%;
    min-height: 220px;
    display: flex;
    flex-direction: column;
}
.tile:hover {
    border-color: #2563eb;
    box-shadow: 0 4px 16px rgba(37, 99, 235, 0.08);
    transform: translateY(-1px);
}
.tile-chip {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    color: white;
    margin-bottom: 10px;
    letter-spacing: 0.02em;
}
.tile-headline {
    font-size: 14.5px;
    font-weight: 600;
    color: #0f172a;
    margin: 0 0 8px 0;
    line-height: 1.35;
}
.tile-story {
    font-size: 12.5px;
    color: #64748b;
    line-height: 1.5;
    margin: 0 0 14px 0;
    flex-grow: 1;
}

/* ── Headline recommendation card ───────────────────────────────── */
.headline-card {
    background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
    color: white;
    padding: 28px 30px;
    border-radius: 16px;
    margin: 8px 0 22px 0;
    box-shadow: 0 4px 20px rgba(37, 99, 235, 0.15);
}
.headline-card-eyebrow {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    opacity: 0.85;
    margin: 0 0 10px 0;
}
.headline-card-body {
    font-size: 1.22rem;
    font-weight: 500;
    line-height: 1.5;
    margin: 0;
}
.headline-action {
    font-weight: 700;
    background: rgba(255,255,255,0.18);
    padding: 2px 10px;
    border-radius: 6px;
}

/* ── Section labels (bumped for clinician readability) ──────────── */
.section-label {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    color: #475569;
    margin: 22px 0 8px 0;
    padding-bottom: 4px;
    border-bottom: 1px solid #e2e8f0;
}

/* ── Stat cards ─────────────────────────────────────────────────── */
.stat-card {
    background: #f8fafc;
    border-left: 3px solid #2563eb;
    padding: 12px 16px;
    border-radius: 6px;
    margin-bottom: 8px;
}
.stat-card-label {
    font-size: 12.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #475569;
    margin: 0 0 4px 0;
}
.stat-card-value {
    font-size: 1.15rem;
    font-weight: 700;
    color: #0f172a;
    margin: 0;
}

/* ── Q&A answer card ────────────────────────────────────────────── */
.qa-card {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 16px 18px;
    background: #ffffff;
    margin-bottom: 14px;
}
.qa-card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid #f1f5f9;
}
.qa-tag {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    padding: 3px 9px;
    border-radius: 4px;
    background: #eff6ff;
    color: #1d4ed8;
}
.qa-n {
    font-size: 12px;
    color: #64748b;
}

/* ── Method comparison ──────────────────────────────────────────── */
.method-pill {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 11.5px;
    font-weight: 600;
    margin-right: 6px;
    margin-bottom: 6px;
}
.method-ours { background: #dcfce7; color: #166534; }
.method-baseline { background: #f1f5f9; color: #475569; }

/* ── Footer ─────────────────────────────────────────────────────── */
.footer {
    margin-top: 48px;
    padding-top: 18px;
    border-top: 1px solid #e2e8f0;
    font-size: 12px;
    color: #64748b;
    text-align: center;
    line-height: 1.7;
}
.footer a { color: #2563eb; text-decoration: none; }
.footer a:hover { text-decoration: underline; }

/* ── Subtle info / warn banners ─────────────────────────────────── */
.info-line {
    background: #f8fafc;
    border-left: 3px solid #cbd5e1;
    padding: 10px 14px;
    border-radius: 4px;
    font-size: 13.5px;
    color: #334155;
    margin-bottom: 12px;
    line-height: 1.55;
}
.warn-line {
    background: #fffbeb;
    border-left: 3px solid #f59e0b;
    padding: 10px 14px;
    border-radius: 4px;
    font-size: 13.5px;
    color: #78350f;
    margin-bottom: 12px;
    line-height: 1.55;
}

/* ── Persistent experimental banner ─────────────────────────────── */
.banner {
    background: #fef3c7;
    border-top: 1px solid #fcd34d;
    border-bottom: 1px solid #fcd34d;
    color: #78350f;
    font-size: 12.5px;
    font-weight: 600;
    text-align: center;
    padding: 6px 14px;
    letter-spacing: 0.02em;
    margin: 0 -1rem 14px -1rem;
}

/* ── Responsive nav ─────────────────────────────────────────────── */
@media (max-width: 760px) {
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }
    [data-testid="stHorizontalBlock"] > div {
        flex: 1 1 50% !important;
        min-width: 0 !important;
    }
}
@media (max-width: 480px) {
    [data-testid="stHorizontalBlock"] > div {
        flex: 1 1 100% !important;
    }
}

/* ── Method-step diagram ────────────────────────────────────────── */
.step {
    display: flex;
    gap: 16px;
    padding: 14px 0;
    border-bottom: 1px solid #f1f5f9;
}
.step-num {
    flex: 0 0 32px;
    height: 32px;
    border-radius: 999px;
    background: #eff6ff;
    color: #2563eb;
    font-weight: 700;
    font-size: 13px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.step-body { flex: 1; }
.step-title {
    font-size: 14px;
    font-weight: 600;
    color: #0f172a;
    margin: 4px 0 4px 0;
}
.step-desc {
    font-size: 12.5px;
    color: #64748b;
    line-height: 1.55;
    margin: 0;
}
/* ── Starter question buttons — allow full text, no truncation ───── */
div[data-testid="stButton"] > button {
    height: auto !important;
    min-height: 2.5rem !important;
    white-space: normal !important;
    text-align: left !important;
    line-height: 1.45 !important;
    padding-top: 10px !important;
    padding-bottom: 10px !important;
    justify-content: flex-start !important;
}
div[data-testid="stButton"] > button p {
    text-align: left !important;
    width: 100%;
}
/* ── Hide sidebar entirely — top nav is the only navigation ─────── */
[data-testid="stSidebar"] {
    display: none !important;
}
[data-testid="collapsedControl"] {
    display: none !important;
}
/* ── Hide sidebar entirely ──────────────────────────────────────── */
[data-testid="stSidebar"] {
    display: none !important;
}
[data-testid="collapsedControl"] {
    display: none !important;
}

.overview-card, .overview-card:visited, .overview-card:active {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 14px 16px;
    background: #fff;
    display: flex;
    flex-direction: column;
    height: 100%;
    text-decoration: none !important;
    transition: all 0.15s ease;
    cursor: pointer;
    position: relative;
    color: inherit;
}
.overview-card * {
    text-decoration: none !important;
}
.overview-card:hover {
    background: #f8fafc;
    border-color: #2563eb;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.10);
    transform: translateY(-1px);
}
.overview-card-arrow {
    display: inline-block;
    margin-left: 4px;
    color: #2563eb;
    font-weight: 700;
    opacity: 0;
    transition: opacity 0.15s ease;
}
.overview-card:hover .overview-card-arrow {
    opacity: 1;
}
/* ── Fix help-tooltip (?) positioning + text alignment ────────────── */
div[data-baseweb="tooltip"] {
    text-align: center !important;
    left: auto !important;
    transform: none !important;
    margin-left: 24px !important;
}
/* ── Question input — make it the visually dominant element ──────── */
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
    border: 2.5px solid #2563eb !important;
    border-radius: 12px !important;
    background: #f8faff !important;
    font-size: 15px !important;
    padding: 14px 16px !important;
    min-height: 100px !important;
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
}
div[data-testid="stTextInput"] input:focus,
div[data-testid="stTextArea"] textarea:focus {
    border-color: #1d4ed8 !important;
    box-shadow: 0 0 0 6px rgba(37, 99, 235, 0.18) !important;
    background: #ffffff !important;
}
</style>
"""


def inject() -> None:
    """Inject the stylesheet. Call once per page near the top."""
    st.markdown(_CSS, unsafe_allow_html=True)


_BANNER_TEXT = ("Experimental Research Demo &nbsp;·&nbsp; Synthetic Data "
                "&nbsp;·&nbsp; Not For Clinical Use")


def banner() -> None:
    """Render the persistent experimental banner.

    Typically called automatically by ``nav.render``; exposed as a public
    helper so a page can re-emit it if a previous element disrupts the flow.
    """
    st.markdown(
        f"<div class='banner'>{_BANNER_TEXT}</div>",
        unsafe_allow_html=True,
    )


def footer() -> None:
    """Render a consistent footer."""
    st.markdown(
        """
        <div class="footer">
            Ask my data · retrospective explorer on a synthetic meningioma cohort
            <br/>
            Not for clinical use. Outputs are illustrative.
        </div>
        """,
        unsafe_allow_html=True,
    )
