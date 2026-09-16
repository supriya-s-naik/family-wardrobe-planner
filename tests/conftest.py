import pytest


@pytest.fixture(autouse=True)
def isolate_application_database(tmp_path, monkeypatch):
    """Keep Streamlit and persistence tests away from the developer's local database."""
    monkeypatch.setenv("WARDROBE_DB_PATH", str(tmp_path / "wardrobe-planner-test.db"))
