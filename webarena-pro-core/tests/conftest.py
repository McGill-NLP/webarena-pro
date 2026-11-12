import pytest


@pytest.fixture(autouse=True)
def isolated_eval_token_config(monkeypatch, tmp_path):
    """Tests must neither use deployment secrets nor create user token files."""
    monkeypatch.delenv("WP_EVAL_TOKEN", raising=False)
    monkeypatch.setenv("WP_EVAL_TOKEN_FILE", str(tmp_path / "eval-token"))
