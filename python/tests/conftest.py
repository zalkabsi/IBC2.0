import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets its own ibc2 home and no inherited IBC2_* settings."""
    import os

    for key in list(os.environ):
        if key.startswith("IBC2_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("IBC2_HOME", str(tmp_path / "home"))
    return tmp_path / "home"
