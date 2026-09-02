"""An empty credential var must not shadow the SDK's resolution chain."""

import importlib
import os

import pytest


@pytest.mark.parametrize("var", ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"])
def test_empty_credential_var_is_dropped(monkeypatch, var):
    monkeypatch.setenv(var, "")
    import tapewatch.config

    importlib.reload(tapewatch.config)
    assert var not in os.environ, (
        f"an empty {var} shadows the SDK's other credential sources and "
        'fails with "Could not resolve authentication method"'
    )


def test_real_credential_is_left_alone(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    import tapewatch.config

    importlib.reload(tapewatch.config)
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-not-a-real-key"
