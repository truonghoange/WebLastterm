"""All pytest runs use isolated local storage, including existing UI regressions."""
import pytest


@pytest.fixture(autouse=True)
def isolated_workspace_database(tmp_path, monkeypatch):
    monkeypatch.setenv("CVISION_DB_PATH", str(tmp_path / "cvision-test.db"))
