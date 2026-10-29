import json
import os
import unittest
from unittest import mock

from stubs import FakeResponse, load_plugin

CATALOG = {
    "data": [
        {
            "id": "openai/gpt-5.6-sol-pro",
            "type": "openai/chat-completions",
            "capabilities": ["tools"],
            "info": {"isHottest": True},
            "pricing": {
                "units": [
                    {"type": "charge", "name": "token", "content": "text", "measure": "output",
                     "phase": "inference", "origin": "provided", "author": "user",
                     "price": "2.5", "per": "1000000"},
                    {"type": "charge", "name": "token", "content": "text", "measure": "output",
                     "phase": "inference", "origin": "generated", "author": "model",
                     "price": "10", "per": "1000000"},
                ]
            },
        },
        {"id": "brand/new-hot-model", "type": "openai/chat-completions", "info": {"isHottest": True}},
        {"id": "anthropic/claude-sonnet-5", "type": "openai/chat-completions",
         "capabilities": ["tools"], "info": {"isHottest": True}},
        {"id": "vendor/tool-model", "type": "openai/chat-completions", "capabilities": ["tools", "vision"]},
        {"id": "vendor/no-tools", "type": "openai/chat-completions", "capabilities": ["vision"]},
        {"id": "vendor/image-model", "type": "image", "capabilities": ["tools"]},
        "not-a-dict",
    ]
}


def _catalog_response(*_args, **_kwargs):
    return FakeResponse(json.dumps(CATALOG).encode())


class ProfileRegistrationTest(unittest.TestCase):
    def test_registers_one_api_key_provider(self):
        plugin, rec = load_plugin()
        [profile] = rec.registered
        self.assertIs(profile, plugin.aimlapi)
        self.assertEqual(profile.name, "aimlapi")
        self.assertEqual(profile.env_vars, ("AIMLAPI_API_KEY",))
        self.assertEqual(profile.base_url, "https://api.aimlapi.com/v1")
        self.assertTrue(profile.aggregator)
        self.assertIsNotNone(profile.model_setup_flow)

    def test_legacy_profile_shape_still_registers(self):
        plugin, rec = load_plugin(legacy=True)
        [profile] = rec.registered
        self.assertEqual(profile.name, "aimlapi")
        self.assertFalse(hasattr(profile, "model_setup_flow"))
        self.assertFalse(hasattr(profile, "aggregator"))


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.plugin, _ = load_plugin()
        self.profile = self.plugin.aimlapi

    def test_hottest_first_then_tool_capable_chat_models(self):
        with mock.patch("urllib.request.urlopen", side_effect=_catalog_response):
            models = self.profile.fetch_models(api_key="k")
        self.assertEqual(
            models,
            ["anthropic/claude-sonnet-5", "openai/gpt-5.6-sol-pro", "brand/new-hot-model", "vendor/tool-model"],
        )

    def test_catalog_is_fetched_once_and_shared_with_pricing(self):
        with mock.patch("urllib.request.urlopen", side_effect=_catalog_response) as urlopen:
            self.profile.fetch_models()
            pricing = self.profile.fetch_model_pricing()
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(
            pricing, {"openai/gpt-5.6-sol-pro": {"prompt": "0.0000025", "completion": "0.00001"}}
        )

    def test_untrusted_base_url_is_never_fetched(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            self.assertIsNone(self.profile.fetch_models(base_url="https://proxy.example.com/v1"))
            self.assertEqual(self.profile.fetch_model_pricing(base_url="http://api.aimlapi.com/v1"), {})
        urlopen.assert_not_called()

    def test_network_failure_returns_none(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertIsNone(self.profile.fetch_models())


class AttributionTest(unittest.TestCase):
    def setUp(self):
        self.plugin, _ = load_plugin()
        self.profile = self.plugin.aimlapi

    def test_no_attribution_headers_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.profile.build_api_kwargs_extras(base_url=self.profile.base_url), ({}, {}))
            with mock.patch("urllib.request.urlopen", side_effect=_catalog_response) as urlopen:
                self.profile.fetch_models()
        request = urlopen.call_args.args[0]
        self.assertFalse([h for h in request.headers if h.lower().startswith("x-aimlapi")])

    def test_opt_in_adds_headers_on_aimlapi_hosts_only(self):
        with mock.patch.dict(os.environ, {"AIMLAPI_ATTRIBUTION": "1"}, clear=True):
            _, top = self.profile.build_api_kwargs_extras(base_url="https://api.aimlapi.com/v1")
            _, other = self.profile.build_api_kwargs_extras(base_url="https://proxy.example.com/v1")
        self.assertEqual(top["extra_headers"]["X-AIMLAPI-Partner-ID"], "part_H9mK4xR7vT2qN8pL5cY3wBfD")
        self.assertEqual(top["extra_headers"]["X-AIMLAPI-Source"], "agent/hermes-agent")
        self.assertEqual(other, {})


if __name__ == "__main__":
    unittest.main()
