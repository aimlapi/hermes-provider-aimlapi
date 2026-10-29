import unittest
from unittest import mock

from stubs import load_plugin


class ModelSetupFlowTest(unittest.TestCase):
    def setUp(self):
        self.plugin, self.rec = load_plugin()
        from aimlapi import onboarding, setup_flow

        self.setup_flow = setup_flow
        self.onboarding = onboarding
        self.profile = self.plugin.aimlapi
        interactive = mock.patch.object(setup_flow, "_interactive", return_value=True)
        interactive.start()
        self.addCleanup(interactive.stop)
        self.catalog = mock.patch.object(type(self.profile), "fetch_models", return_value=["m/one", "m/two"])
        self.pricing = mock.patch.object(
            type(self.profile), "fetch_model_pricing", return_value={"m/one": {"prompt": "1", "completion": "2"}}
        )
        self.catalog.start()
        self.pricing.start()
        self.addCleanup(self.catalog.stop)
        self.addCleanup(self.pricing.stop)

    def _run(self, key, current_model=""):
        with mock.patch.object(self.onboarding, "guided_api_key_setup", return_value=key) as guided:
            self.profile.model_setup_flow({}, current_model, None)
        return guided

    def test_new_key_is_saved_and_the_pick_persisted(self):
        self.rec.picker_answer = "m/two"
        guided = self._run("fresh-key", current_model="m/one")
        guided.assert_called_once_with("")
        self.assertEqual(self.rec.saved_env, [("AIMLAPI_API_KEY", "fresh-key")])
        [(models, kwargs)] = self.rec.picker_calls
        self.assertEqual(models, ["m/one", "m/two"])
        self.assertEqual(kwargs["pricing"], {"m/one": {"prompt": "1", "completion": "2"}})
        self.assertEqual(kwargs["current_model"], "m/one")
        self.assertEqual(kwargs["confirm_provider"], "aimlapi")
        self.assertEqual(kwargs["confirm_api_key"], "fresh-key")
        self.assertEqual(
            self.rec.persisted, [("m/two", "aimlapi", {"base_url": "https://api.aimlapi.com/v1"})]
        )

    def test_saved_key_is_offered_and_not_rewritten(self):
        self.rec.secrets["AIMLAPI_API_KEY"] = "saved-key"
        self.rec.picker_answer = "m/one"
        guided = self._run("saved-key")
        guided.assert_called_once_with("saved-key")
        self.assertEqual(self.rec.saved_env, [])
        self.assertEqual(len(self.rec.persisted), 1)

    def test_no_key_means_no_picker_and_an_auth_failure(self):
        self._run(None)
        self.assertEqual(self.rec.failures, ["auth"])
        self.assertEqual(self.rec.picker_calls, [])
        self.assertEqual(self.rec.persisted, [])

    def test_skipping_the_picker_changes_nothing(self):
        self.rec.picker_answer = None
        self._run("fresh-key")
        self.assertEqual(self.rec.persisted, [])

    def test_offline_catalog_falls_back_to_curated_models(self):
        self.rec.picker_answer = "anthropic/claude-sonnet-5"
        with mock.patch.object(type(self.profile), "fetch_models", return_value=None):
            self._run("fresh-key")
        [(models, _kwargs)] = self.rec.picker_calls
        self.assertEqual(tuple(models), self.plugin.CURATED_MODELS)

    def test_unattended_run_stops_before_any_prompt(self):
        with mock.patch.object(self.setup_flow, "_interactive", return_value=False):
            guided = self._run("never")
        guided.assert_not_called()
        self.assertEqual(self.rec.failures, ["auth"])
        self.assertTrue(any("interactive terminal" in line for line in self.rec.output))


if __name__ == "__main__":
    unittest.main()
