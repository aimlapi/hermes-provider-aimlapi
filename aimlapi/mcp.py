"""Opt-in aimlapi.com MCP server entry for Hermes (``mcp_servers.aimlapi``).

The aimlapi.com MCP server (``https://mcp.aimlapi.com/mcp``, Streamable HTTP,
stateless) gives the agent model discovery, account balance and usage,
image/video/audio generation, chat, embeddings and the aimlapi.com Toolbox.
Generation and Toolbox runs are billed to the user's balance, so nothing here
runs unless the user says yes in the ``hermes model`` step.

The entry goes into the user's ``config.yaml`` through ``hermes_cli.config``:

- the key is an environment reference, ``Bearer ${AIMLAPI_API_KEY}``, which
  Hermes resolves at connect time from the profile's ``.env``; the key itself
  is never written to ``config.yaml``;
- when the aimlapi.com provider points anywhere but ``https://api.aimlapi.com``
  (a proxy, a gateway, a staging host), ``AIMLAPI_API_KEY`` may be that
  endpoint's credential, so the entry carries no key and uses the server's
  OAuth sign-in instead;
- ``trust: untrusted`` makes Hermes ask before every tool call the server does
  not mark read-only, i.e. every billed call;
- attribution headers follow ``AIMLAPI_ATTRIBUTION`` (off by default) and are
  only ever attached for the exact host ``mcp.aimlapi.com``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .config import API_KEY_ENV, PROVIDER_ID, attribution_headers, is_attribution_host

SERVER_NAME = "aimlapi"
MCP_URL = "https://mcp.aimlapi.com/mcp"
CANONICAL_API_HOST = "api.aimlapi.com"
KEY_REFERENCE = "${" + API_KEY_ENV + "}"


def is_canonical_api_url(value: str | None) -> bool:
    """True only for ``https://api.aimlapi.com[...]`` with no credentials or custom port."""
    value = (value or "").strip()
    return is_attribution_host(value) and (urlparse(value).hostname or "").lower() == CANONICAL_API_HOST


def configured_base_urls(profile_base_url: str, config: dict[str, Any] | None) -> list[str]:
    """Every base URL the aimlapi.com provider may be using in this profile."""
    urls = [profile_base_url]
    model = (config or {}).get("model")
    if isinstance(model, dict) and str(model.get("provider") or "").strip() == PROVIDER_ID:
        base_url = str(model.get("base_url") or "").strip()
        if base_url:
            urls.append(base_url)
    return urls


def key_belongs_to_aimlapi(profile_base_url: str, config: dict[str, Any] | None) -> bool:
    """Whether ``AIMLAPI_API_KEY`` is an aimlapi.com key (no proxy in between)."""
    return all(is_canonical_api_url(url) for url in configured_base_urls(profile_base_url, config))


def server_entry(*, send_key: bool, url: str = MCP_URL) -> dict[str, Any]:
    """The ``mcp_servers.aimlapi`` entry; the key is only ever a ``${...}`` reference."""
    headers: dict[str, str] = {}
    if is_attribution_host(url):
        headers.update(attribution_headers())
    entry: dict[str, Any] = {"url": url}
    if send_key and is_attribution_host(url):
        headers["Authorization"] = f"Bearer {KEY_REFERENCE}"
    else:
        entry["auth"] = "oauth"
    if headers:
        entry["headers"] = headers
    entry["trust"] = "untrusted"
    return entry


def existing_entry(config: dict[str, Any] | None) -> Any:
    servers = (config or {}).get("mcp_servers")
    return servers.get(SERVER_NAME) if isinstance(servers, dict) else None


def add_server(profile_base_url: str) -> tuple[str, dict[str, Any] | None]:
    """Write the entry unless one exists. Returns ``(outcome, entry)``.

    ``outcome`` is ``"exists"`` (left untouched), ``"key"`` (Bearer reference)
    or ``"oauth"`` (no key: the provider points at a non-aimlapi.com endpoint).
    """
    from hermes_cli.config import load_config, save_config

    config = load_config()
    if existing_entry(config) is not None:
        return "exists", None
    send_key = key_belongs_to_aimlapi(profile_base_url, config)
    entry = server_entry(send_key=send_key)
    servers = config.get("mcp_servers")
    if not isinstance(servers, dict):
        servers = {}
        config["mcp_servers"] = servers
    servers[SERVER_NAME] = entry
    save_config(config)
    return ("key" if send_key else "oauth"), entry
