"""The aimlapi.com ``hermes model`` step (``ProviderProfile.model_setup_flow``).

Uses only the documented plugin helpers: ``agent.secret_scope.get_secret`` to
read the saved key, ``hermes_cli.config`` to save a new one,
``hermes_cli.auth_model_picker.prompt_model_selection`` for the picker and
``hermes_cli.model_setup`` to persist the choice.
"""

from __future__ import annotations

import sys
from typing import Any

from .config import API_KEY_ENV, PROVIDER_ID


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _saved_key() -> str:
    from agent.secret_scope import get_secret

    return (get_secret(API_KEY_ENV) or "").strip()


def _save_key(api_key: str) -> None:
    from hermes_cli import config as hermes_config

    save = getattr(hermes_config, "save_env_value_secure", None) or hermes_config.save_env_value
    save(API_KEY_ENV, api_key)


def run_model_setup(profile: Any, config: Any, current_model: str = "", args: Any = None) -> None:
    del config, args
    from hermes_cli.auth_model_picker import prompt_model_selection
    from hermes_cli.cli_output import print_error, print_info, print_success
    from hermes_cli.model_setup import note_setup_failure, persist_model_selection

    from .onboarding import guided_api_key_setup

    if not _interactive():
        print_error(
            "aimlapi.com setup needs an interactive terminal: run `hermes model` in a "
            f"terminal, or set {API_KEY_ENV} in your Hermes .env."
        )
        note_setup_failure("auth")
        return

    existing_key = _saved_key()
    api_key = guided_api_key_setup(existing_key)
    if not api_key:
        note_setup_failure("auth")
        return
    if api_key != existing_key:
        _save_key(api_key)

    base_url = profile.base_url
    models = profile.fetch_models(api_key=api_key, base_url=base_url)
    if models:
        print_info(f"Found {len(models)} model(s) on aimlapi.com.")
    else:
        models = list(profile.fallback_models)
    if not models:
        print_error("aimlapi.com returned no models — try again later.")
        note_setup_failure("no_models")
        return

    selected = prompt_model_selection(
        models,
        current_model=current_model,
        pricing=profile.fetch_model_pricing(base_url=base_url) or None,
        confirm_provider=PROVIDER_ID,
        confirm_base_url=base_url,
        confirm_api_key=api_key,
    )
    if not selected:
        print("No change.")
        return
    persist_model_selection(selected, PROVIDER_ID, base_url=base_url)
    print_success(f"Default model set to: {selected} (via aimlapi.com)")
