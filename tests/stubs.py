"""Stand-ins for the Hermes modules the plugin touches, so tests run offline
without a Hermes checkout. ``load_plugin()`` installs them and (re)imports the
plugin package against either the current ``ProviderProfile`` shape or a
legacy one that predates ``model_setup_flow`` and ``aggregator``.
"""

from __future__ import annotations

import dataclasses
import importlib
import sys
import types
from collections import deque
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclasses.dataclass
class LegacyProviderProfile:
    name: str
    api_mode: str = "chat_completions"
    aliases: tuple = ()
    display_name: str = ""
    description: str = ""
    signup_url: str = ""
    env_vars: tuple = ()
    base_url: str = ""
    models_url: str = ""
    auth_type: str = "api_key"
    supports_vision: bool = False
    fallback_models: tuple = ()
    default_aux_model: str = ""

    def build_api_kwargs_extras(self, *, reasoning_config=None, **context):
        return {}, {}

    def fetch_models(self, *, api_key=None, base_url=None, timeout=8.0):
        return None


@dataclasses.dataclass
class ModernProviderProfile(LegacyProviderProfile):
    aggregator: bool = False
    model_setup_flow: Callable[[Any, str, Any], Any] | None = None


class Recorder:
    """Shared state the stub Hermes modules read from and write to."""

    def __init__(self) -> None:
        self.registered: list[Any] = []
        self.secrets: dict[str, str] = {}
        self.saved_env: list[tuple[str, str]] = []
        self.persisted: list[tuple[str, str, dict]] = []
        self.failures: list[str] = []
        self.picker_calls: list[tuple[list, dict]] = []
        self.picker_answer: str | None = None
        self.inputs: deque = deque()
        self.output: list[str] = []

    def answer(self, *values: Any) -> None:
        """Queue answers for ``line_input``; an exception instance is raised instead."""
        self.inputs.extend(values)


def _module(name: str, **attrs: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    return module


def install(rec: Recorder, profile_cls: type) -> None:
    def line_input(prompt_text: str) -> str:
        rec.output.append(prompt_text)
        value = rec.inputs.popleft()
        if isinstance(value, BaseException):
            raise value
        return value

    def printer(prefix: str):
        return lambda text: rec.output.append(f"{prefix}{text}")

    def prompt_model_selection(model_ids, **kwargs):
        rec.picker_calls.append((list(model_ids), kwargs))
        return rec.picker_answer

    providers = _module("providers", register_provider=rec.registered.append)
    providers.__path__ = []
    modules = {
        "providers": providers,
        "providers.base": _module("providers.base", ProviderProfile=profile_cls),
        "agent": _module("agent", __path__=[]),
        "agent.secret_scope": _module(
            "agent.secret_scope", get_secret=lambda name, default=None: rec.secrets.get(name, default)
        ),
        "hermes_cli": _module("hermes_cli", __path__=[]),
        "hermes_cli.cli_output": _module(
            "hermes_cli.cli_output",
            line_input=line_input,
            print_info=printer("info: "),
            print_success=printer("ok: "),
            print_warning=printer("warn: "),
            print_error=printer("error: "),
            print_header=printer("header: "),
        ),
        "hermes_cli.config": _module(
            "hermes_cli.config",
            save_env_value_secure=lambda key, value: rec.saved_env.append((key, value)),
        ),
        "hermes_cli.model_setup": _module(
            "hermes_cli.model_setup",
            persist_model_selection=lambda model, provider, **kw: rec.persisted.append((model, provider, kw)),
            note_setup_failure=rec.failures.append,
        ),
        "hermes_cli.auth_model_picker": _module(
            "hermes_cli.auth_model_picker", prompt_model_selection=prompt_model_selection
        ),
    }
    sys.modules.update(modules)
    sys.modules["hermes_cli"].cli_output = modules["hermes_cli.cli_output"]
    sys.modules["hermes_cli"].config = modules["hermes_cli.config"]


def load_plugin(*, legacy: bool = False) -> tuple[types.ModuleType, Recorder]:
    rec = Recorder()
    install(rec, LegacyProviderProfile if legacy else ModernProviderProfile)
    for name in [m for m in sys.modules if m == "aimlapi" or m.startswith("aimlapi.")]:
        del sys.modules[name]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    plugin = importlib.import_module("aimlapi")
    plugin._catalog_cache.clear()
    return plugin, rec


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit < 0 else self._body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
