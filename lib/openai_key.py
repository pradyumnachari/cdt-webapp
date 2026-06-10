"""
Resolve an OpenAI API key without ever asking the user to paste it in the UI.

Lookup order:
    1. Streamlit secrets — `.streamlit/secrets.toml` -> key `openai_api_key`
    2. Environment variable — `OPENAI_API_KEY`

If neither is set, returns None and the Q&A renders a one-time setup hint.
Nothing is ever logged.
"""

from __future__ import annotations

import os
from typing import Optional

import streamlit as st


def get_key() -> Optional[str]:
    try:
        if "openai_api_key" in st.secrets and st.secrets["openai_api_key"]:
            return str(st.secrets["openai_api_key"])
    except Exception:  # noqa: BLE001  — st.secrets raises if file absent
        pass
    env = os.environ.get("OPENAI_API_KEY") or os.environ.get("openai_api_key")
    return env or None


def render_missing_key_panel() -> None:
    """Show a friendly setup hint when no key is available."""
    st.markdown(
        """
        <div class="warn-line">
            <b>OpenAI key not configured.</b> Q&amp;A is grounded — every
            number is computed by the app, the model only writes the prose —
            but it needs an LLM for that.
            <br/><br/>
            <b>Set it up once</b> (local self-host only — the hosted demo
            has a key configured for you): create
            <code>cdt_webapp_v4/.streamlit/secrets.toml</code> with one line:
            <pre style="margin:8px 0 4px 0;padding:8px 10px;background:#fff7ed;
                        border-radius:4px;font-size:11.5px;color:#7c2d12;">
openai_api_key = "sk-..."
            </pre>
            Then refresh this page. The file is gitignored.
        </div>
        """,
        unsafe_allow_html=True,
    )
