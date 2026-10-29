"""Load the plugin through real Hermes provider discovery and check the seams it uses.

Run with the Hermes interpreter and ``HERMES_HOME`` pointing at a home whose
``plugins/model-providers/aimlapi`` is this repo's ``aimlapi`` directory (CI does
this). Needs no network: nothing here fetches the catalog or calls the API.
"""

from __future__ import annotations

import dataclasses
import inspect
import os

from providers import get_provider_profile
from providers.base import ProviderProfile

profile = get_provider_profile("aimlapi")
assert profile is not None, "aimlapi did not register through provider discovery"
assert profile.env_vars == ("AIMLAPI_API_KEY",), profile.env_vars
assert profile.base_url == "https://api.aimlapi.com/v1", profile.base_url
assert get_provider_profile("ai-ml-api") is profile

os.environ.pop("AIMLAPI_ATTRIBUTION", None)
_, top_level = profile.build_api_kwargs_extras(base_url=profile.base_url)
assert "extra_headers" not in top_level, top_level
os.environ["AIMLAPI_ATTRIBUTION"] = "1"
_, top_level = profile.build_api_kwargs_extras(base_url=profile.base_url)
assert top_level["extra_headers"]["X-AIMLAPI-Partner-ID"] == "part_H9mK4xR7vT2qN8pL5cY3wBfD", top_level
os.environ.pop("AIMLAPI_ATTRIBUTION")

fields = {f.name for f in dataclasses.fields(ProviderProfile)}
if "model_setup_flow" in fields:
    from agent.secret_scope import get_secret  # noqa: F401
    from hermes_cli.auth_model_picker import prompt_model_selection
    from hermes_cli.cli_output import (  # noqa: F401
        line_input,
        print_error,
        print_header,
        print_info,
        print_success,
        print_warning,
    )
    from hermes_cli.config import save_env_value  # noqa: F401
    from hermes_cli.model_setup import note_setup_failure, persist_model_selection  # noqa: F401
    from hermes_cli.model_setup_flows import _profile_model_setup_flow

    assert _profile_model_setup_flow("aimlapi") is profile.model_setup_flow
    picker = set(inspect.signature(prompt_model_selection).parameters)
    assert {"current_model", "pricing", "confirm_provider", "confirm_base_url", "confirm_api_key"} <= picker
    assert "base_url" in inspect.signature(persist_model_selection).parameters
    # stdin is not a TTY here: the step must refuse cleanly, without prompting.
    profile.model_setup_flow({}, "", None)
    print("model_setup_flow: present, wired, refuses unattended runs")
else:
    print("model_setup_flow: not in this Hermes build (generic API-key flow)")

print("aimlapi plugin smoke test passed")
