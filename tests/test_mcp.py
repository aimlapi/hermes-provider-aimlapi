import json
import os
import unittest
from unittest import mock

from stubs import load_plugin

KEY = "sk-live-secret-value-123"
PARTNER = "part_H9mK4xR7vT2qN8pL5cY3wBfD"


class McpEntryTest(unittest.TestCase):
    def setUp(self):
        self.plugin, self.rec = load_plugin()
        from aimlapi import config, mcp

        self.mcp = mcp
        self.config = config

    def test_exact_host_gate(self):
        allowed = [
            "https://mcp.aimlapi.com/mcp",
            "https://MCP.aimlapi.com/mcp",
            "https://api.aimlapi.com/v1",
            "https://mcp.aimlapi.com:443/mcp",
        ]
        refused = [
            "http://mcp.aimlapi.com/mcp",
            "https://tools.aimlapi.com/v1",
            "https://aimlapi.com/mcp",
            "https://evil.mcp.aimlapi.com/mcp",
            "https://mcp.aimlapi.com.evil.com/mcp",
            "https://mcp.aimlapi.com@evil.com/mcp",
            "https://user:pw@mcp.aimlapi.com/mcp",
            "https://mcp.aimlapi.com:8443/mcp",
            "https://mcp-aimlapi.com/mcp",
            "not a url",
        ]
        for url in allowed:
            self.assertTrue(self.config.is_attribution_host(url), url)
        for url in refused:
            self.assertFalse(self.config.is_attribution_host(url), url)

    def test_attribution_only_on_exact_host_and_only_when_opted_in(self):
        with mock.patch.dict(os.environ, {"AIMLAPI_ATTRIBUTION": "1"}, clear=True):
            ours = self.mcp.server_entry(send_key=True)
            other = self.mcp.server_entry(send_key=True, url="https://mcp.aimlapi.com.evil.com/mcp")
            sibling = self.mcp.server_entry(send_key=True, url="https://tools.aimlapi.com/mcp")
        self.assertEqual(ours["headers"]["X-AIMLAPI-Partner-ID"], PARTNER)
        self.assertEqual(ours["headers"]["X-AIMLAPI-Source"], "agent/hermes-agent")
        for entry in (other, sibling):
            self.assertNotIn("headers", entry)
            self.assertEqual(entry["auth"], "oauth")
        with mock.patch.dict(os.environ, {}, clear=True):
            plain = self.mcp.server_entry(send_key=True)
        self.assertEqual(plain["headers"], {"Authorization": "Bearer ${AIMLAPI_API_KEY}"})

    def test_entry_is_untrusted_and_carries_only_a_key_reference(self):
        entry = self.mcp.server_entry(send_key=True)
        self.assertEqual(entry["url"], "https://mcp.aimlapi.com/mcp")
        self.assertEqual(entry["trust"], "untrusted")
        self.assertEqual(entry["headers"]["Authorization"], "Bearer ${AIMLAPI_API_KEY}")
        self.assertNotIn("auth", entry)

    def test_proxy_base_url_means_no_key(self):
        self.assertTrue(self.mcp.key_belongs_to_aimlapi("https://api.aimlapi.com/v1", {}))
        for base in (
            "https://proxy.example.com/v1",
            "https://api.staging.aimlapi.com/v1",
            "http://api.aimlapi.com/v1",
            "https://api.aimlapi.com:8443/v1",
        ):
            self.assertFalse(self.mcp.key_belongs_to_aimlapi(base, {}), base)
        proxied_config = {"model": {"provider": "aimlapi", "base_url": "https://llm-proxy.corp/v1"}}
        self.assertFalse(self.mcp.key_belongs_to_aimlapi("https://api.aimlapi.com/v1", proxied_config))
        other_provider = {"model": {"provider": "openrouter", "base_url": "https://openrouter.ai/api/v1"}}
        self.assertTrue(self.mcp.key_belongs_to_aimlapi("https://api.aimlapi.com/v1", other_provider))

    def test_add_server_writes_reference_never_the_key(self):
        self.rec.secrets["AIMLAPI_API_KEY"] = KEY
        with mock.patch.dict(os.environ, {"AIMLAPI_API_KEY": KEY}, clear=True):
            outcome, _ = self.mcp.add_server("https://api.aimlapi.com/v1")
        self.assertEqual(outcome, "key")
        saved = json.dumps(self.rec.config)
        self.assertNotIn(KEY, saved)
        self.assertEqual(
            self.rec.config["mcp_servers"]["aimlapi"]["headers"]["Authorization"],
            "Bearer ${AIMLAPI_API_KEY}",
        )

    def test_add_server_behind_proxy_uses_oauth(self):
        self.rec.config = {"model": {"provider": "aimlapi", "base_url": "https://llm-proxy.corp/v1"}}
        outcome, entry = self.mcp.add_server("https://api.aimlapi.com/v1")
        self.assertEqual(outcome, "oauth")
        self.assertEqual(entry["auth"], "oauth")
        self.assertNotIn("Authorization", entry.get("headers", {}))
        self.assertNotIn("AIMLAPI_API_KEY", json.dumps(self.rec.config))

    def test_existing_entry_is_never_overwritten(self):
        mine = {"url": "https://mcp.aimlapi.com/mcp", "auth": "oauth"}
        self.rec.config = {"mcp_servers": {"aimlapi": dict(mine), "other": {"url": "https://x.example/mcp"}}}
        outcome, _ = self.mcp.add_server("https://api.aimlapi.com/v1")
        self.assertEqual(outcome, "exists")
        self.assertEqual(self.rec.config_saves, [])
        self.assertEqual(self.rec.config["mcp_servers"]["aimlapi"], mine)


class McpOfferInSetupFlowTest(unittest.TestCase):
    def setUp(self):
        self.plugin, self.rec = load_plugin()
        from aimlapi import onboarding, setup_flow

        self.profile = self.plugin.aimlapi
        self.rec.picker_answer = "m/one"
        for patcher in (
            mock.patch.object(setup_flow, "_interactive", return_value=True),
            mock.patch.object(onboarding, "guided_api_key_setup", return_value=KEY),
            mock.patch.object(type(self.profile), "fetch_models", return_value=["m/one"]),
            mock.patch.object(type(self.profile), "fetch_model_pricing", return_value={}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _run(self, *answers):
        self.rec.answer(*answers)
        self.profile.model_setup_flow({}, "", None)

    def test_off_by_default_importing_the_plugin_writes_nothing(self):
        self.assertEqual(self.rec.config_saves, [])
        self.assertEqual(self.rec.config, {})

    def test_off_by_default_enter_means_no(self):
        self._run("")
        self.assertEqual(self.rec.config_saves, [])
        self.assertIsNone(self.rec.config.get("mcp_servers"))
        self.assertTrue(any("[y/N]" in line for line in self.rec.output))

    def test_eof_or_ctrl_c_means_no(self):
        self._run(KeyboardInterrupt())
        self.assertEqual(self.rec.config_saves, [])
        self._run()  # nothing queued: EOF
        self.assertEqual(self.rec.config_saves, [])

    def test_anything_but_yes_means_no(self):
        for answer in ("n", "no", "sure", "1"):
            self._run(answer)
        self.assertEqual(self.rec.config_saves, [])

    def test_yes_adds_the_entry_with_a_key_reference(self):
        self._run("y")
        entry = self.rec.config["mcp_servers"]["aimlapi"]
        self.assertEqual(entry["url"], "https://mcp.aimlapi.com/mcp")
        self.assertEqual(entry["headers"]["Authorization"], "Bearer ${AIMLAPI_API_KEY}")
        self.assertEqual(entry["trust"], "untrusted")
        self.assertNotIn(KEY, json.dumps(self.rec.config))

    def test_offered_even_when_the_picker_is_skipped(self):
        self.rec.picker_answer = None
        self._run("yes")
        self.assertIn("aimlapi", self.rec.config["mcp_servers"])
        self.assertEqual(self.rec.persisted, [])

    def test_existing_entry_skips_the_question(self):
        self.rec.config = {"mcp_servers": {"aimlapi": {"url": "https://mcp.aimlapi.com/mcp"}}}
        self._run()
        self.assertFalse(any("[y/N]" in line for line in self.rec.output))
        self.assertEqual(self.rec.config_saves, [])

    def test_failed_key_step_never_offers_mcp(self):
        from aimlapi import onboarding

        with mock.patch.object(onboarding, "guided_api_key_setup", return_value=None):
            self._run("y")
        self.assertEqual(self.rec.config_saves, [])


if __name__ == "__main__":
    unittest.main()
