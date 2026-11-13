"""Answer yes to the aimlapi.com MCP question inside real Hermes and check config.yaml.

Same harness as ``hermes_e2e_setup.py`` (guided sign-up and catalog replaced,
everything else is Hermes's own code). Pipe the picker answer and ``y`` into
stdin, e.g. ``printf '1\\ny\\ny\\n'``. Checks that Hermes's own ``save_config``
stored ``Bearer ${AIMLAPI_API_KEY}`` (never the key) and that Hermes's own MCP
config loader resolves that reference from the profile's ``.env``. Skips on
builds without ``model_setup_flow``.
"""

from __future__ import annotations

import dataclasses
import importlib
import os
import sys
from pathlib import Path
from unittest import mock

from providers import get_provider_profile
from providers.base import ProviderProfile

if "model_setup_flow" not in {f.name for f in dataclasses.fields(ProviderProfile)}:
    print("skip: this Hermes build has no model_setup_flow")
    sys.exit(0)

KEY = "e2e-mcp-test-key-0123456789"
home = Path(os.environ["HERMES_HOME"])
profile = get_provider_profile("aimlapi")
package = type(profile).__module__
onboarding = importlib.import_module(f"{package}.onboarding")
setup_flow = importlib.import_module(f"{package}.setup_flow")

with (
    mock.patch.object(setup_flow, "_interactive", return_value=True),
    mock.patch("hermes_cli.curses_ui.curses_radiolist", side_effect=OSError("no curses in CI")),
    mock.patch.object(onboarding, "guided_api_key_setup", return_value=KEY),
    mock.patch.object(type(profile), "fetch_models", return_value=["openai/gpt-5.4-mini"]),
    mock.patch.object(type(profile), "fetch_model_pricing", return_value={}),
):
    profile.model_setup_flow({}, "", None)

import hermes_yaml as yaml  # noqa: E402  (Hermes's YAML wrapper)

raw = (home / "config.yaml").read_text(encoding="utf-8")
assert KEY not in raw, "the API key was written to config.yaml"
entry = yaml.safe_load(raw)["mcp_servers"]["aimlapi"]
assert entry["url"] == "https://mcp.aimlapi.com/mcp", entry
assert entry["headers"]["Authorization"] == "Bearer ${AIMLAPI_API_KEY}", entry
assert entry["trust"] == "untrusted", entry
assert "auth" not in entry, entry

from tools.mcp_tool_config import _load_mcp_config  # noqa: E402

rendered = _load_mcp_config()["aimlapi"]
assert str(rendered["headers"]["Authorization"]) == f"Bearer {KEY}", "reference did not resolve from .env"
print(f"config.yaml mcp_servers.aimlapi: {entry}")
print("aimlapi hermes MCP e2e passed")
