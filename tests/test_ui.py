from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_landing_has_no_streamlit_exception():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    assert not app.exception
    # Landing (no project) uses st.title; with a project the product header is a markdown block.
    assert app.title or any("Deep Research Kit" in m.value for m in app.markdown)
