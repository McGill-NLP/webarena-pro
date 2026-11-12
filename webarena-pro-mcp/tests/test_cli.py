from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from webarena_pro_mcp.cli import main, parser


def test_install_needs_no_agent_credentials(monkeypatch):
    installed = []
    monkeypatch.setattr("webarena_pro_mcp.runtime.install", lambda: installed.append(True))
    assert main(["install"]) == 0
    assert installed == [True]


async def test_service_configuration_has_no_agent_options():
    args = parser().parse_args([
        "serve", "--config", "session.json", "--directory", "evidence", "--socket", "control.sock",
    ])
    assert args.host == "127.0.0.1"
    assert not {"model", "model_api", "api_key_env", "max_tokens", "n_jobs"} & vars(args).keys()


def test_serve_dispatches_without_an_agent(monkeypatch):
    serve = AsyncMock()
    monkeypatch.setattr("webarena_pro_mcp.server.serve", serve)
    assert main([
        "serve", "--config", "session.json", "--directory", "evidence", "--socket", "control.sock",
    ]) == 0
    serve.assert_awaited_once_with(
        Path("session.json"), Path("evidence"), Path("control.sock"), 8000, host="127.0.0.1",
    )


def test_private_finalize_dispatch(monkeypatch):
    finalize = AsyncMock()
    monkeypatch.setattr("webarena_pro_mcp.server.finalize", finalize)
    assert main(["finalize", "--socket", "control.sock", "--timeout", "900"]) == 0
    finalize.assert_awaited_once_with(Path("control.sock"), 900)


@pytest.mark.parametrize("arguments", [
    ["run"], ["list"], ["serve", "--model", "fixture"],
])
def test_standalone_agent_cli_is_removed(arguments):
    with pytest.raises(SystemExit) as exc:
        main(arguments)
    assert exc.value.code == 2
