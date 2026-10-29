"""Drive the aimlapi.com ``hermes model`` step end to end inside real Hermes.

Only the network-facing parts are replaced: the guided sign-up returns a fixed
key and the catalog returns two models. Saving the key, the model picker
(numbered fallback, fed through stdin) and persisting config.yaml are Hermes's
own code. Run with ``HERMES_HOME`` set to a scratch home that has this repo's
``aimlapi`` directory under ``plugins/model-providers`` and pipe ``1`` into
stdin. Skips on builds without ``model_setup_flow``.
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

home = Path(os.environ["HERMES_HOME"])
profile = get_provider_profile("aimlapi")
package = type(profile).__module__
onboarding = importlib.import_module(f"{package}.onboarding")
setup_flow = importlib.import_module(f"{package}.setup_flow")

with (
    mock.patch.object(setup_flow, "_interactive", return_value=True),
    mock.patch.object(onboarding, "guided_api_key_setup", return_value="e2e-test-key"),
    mock.patch.object(type(profile), "fetch_models", return_value=["openai/gpt-5.4-mini", "deepseek/deepseek-v4-flash"]),
    mock.patch.object(
        type(profile),
        "fetch_model_pricing",
        return_value={"openai/gpt-5.4-mini": {"prompt": "0.00000025", "completion": "0.000002"}},
    ),
):
    profile.model_setup_flow({}, "", None)

import hermes_yaml as yaml  # noqa: E402  (Hermes's YAML wrapper)

config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
model = config["model"]
assert model["provider"] == "aimlapi", model
assert model["default"] == "openai/gpt-5.4-mini", model
assert model["base_url"] == "https://api.aimlapi.com/v1", model
env_text = (home / ".env").read_text(encoding="utf-8")
assert "AIMLAPI_API_KEY=e2e-test-key" in env_text.replace('"', "").replace("'", ""), env_text
print(f"config.yaml model section: {model}")
print("aimlapi hermes model e2e passed")
