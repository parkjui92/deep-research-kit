from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_landing_has_no_streamlit_exception():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    assert not app.exception
    assert app.title
