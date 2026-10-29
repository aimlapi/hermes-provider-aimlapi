import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from stubs import FakeResponse, load_plugin


class ClientTest(unittest.TestCase):
    def setUp(self):
        load_plugin()
        from aimlapi import client, config

        self.client_mod = client
        self.config = config
        self.client = client.AimlapiClient(config.resolve_endpoints())

    def _respond(self, payload, status=200):
        return mock.patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(json.dumps(payload).encode(), status=status),
        )

    def test_checkout_session_carries_the_partner_id(self):
        with mock.patch.dict(os.environ, {}, clear=True), self._respond({"sessionToken": "s1"}) as urlopen:
            self.assertEqual(self.client.create_checkout_session(), "s1")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://app.aimlapi.com/v3/partner-checkout/sessions")
        self.assertEqual(
            json.loads(request.data),
            {"partnerId": "part_H9mK4xR7vT2qN8pL5cY3wBfD", "partnerName": "hermes-agent",
             "returnUrl": "https://aimlapi.com/app"},
        )
        self.assertFalse([h for h in request.headers if h.lower().startswith("x-aimlapi")])

    def test_attribution_headers_only_when_opted_in(self):
        with mock.patch.dict(os.environ, {"AIMLAPI_ATTRIBUTION": "true"}, clear=True), \
                self._respond({"action": "sign-up"}) as urlopen:
            self.client.check_account("a@b.co")
        headers = {k.lower(): v for k, v in urlopen.call_args.args[0].headers.items()}
        self.assertEqual(headers["x-aimlapi-partner-id"], "part_H9mK4xR7vT2qN8pL5cY3wBfD")

    def test_rejected_bearer_hides_the_server_detail(self):
        error = urllib.error.HTTPError("u", 401, "no", {}, io.BytesIO(b"secret detail"))
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(self.client_mod.APIError) as ctx:
                self.client.validate_api_key("bad")
        self.assertEqual(ctx.exception.status, 401)
        self.assertIn("authentication was rejected", str(ctx.exception))

    def test_billing_probe_goes_to_the_api_host(self):
        with self._respond({}) as urlopen:
            self.client.validate_api_key("good")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.aimlapi.com/v2/billing")
        self.assertEqual(request.headers["Authorization"], "Bearer good")

    def test_checkout_url_must_be_aimlapi_or_stripe(self):
        validate = self.client_mod.AimlapiClient._validate_checkout_url
        self.assertEqual(validate("https://checkout.stripe.com/c/pay"), "https://checkout.stripe.com/c/pay")
        self.assertEqual(validate("https://pay.aimlapi.com/x"), "https://pay.aimlapi.com/x")
        for bad in ("http://checkout.stripe.com/x", "https://evil.example/x", "https://u:p@pay.aimlapi.com/x"):
            with self.assertRaises(self.client_mod.APIError):
                validate(bad)

    def test_untrusted_endpoint_is_refused_before_any_request(self):
        endpoints = self.config.Endpoints(
            auth_base_url="https://auth.example.com", app_base_url="https://app.aimlapi.com",
            inference_base_url="https://api.aimlapi.com/v1", pay_base_url="https://pay.aimlapi.com",
            verification_base_url="https://aimlapi.com/app",
        )
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(ValueError):
                self.client_mod.AimlapiClient(endpoints).check_account("a@b.co")
        urlopen.assert_not_called()

    def test_wait_for_checkout_outcomes(self):
        with mock.patch.object(self.client, "get_checkout_session", return_value={"status": "paid", "sessionToken": "paid"}):
            self.assertEqual(self.client.wait_for_checkout("s", poll_interval=0), "paid")
        for status in ("cancelled", "expired", "failed", "exchanged"):
            with mock.patch.object(self.client, "get_checkout_session", return_value={"status": status}):
                with self.assertRaises(self.client_mod.APIError):
                    self.client.wait_for_checkout("s", poll_interval=0)
        with mock.patch.object(self.client, "get_checkout_session", return_value={"status": "pending"}):
            with self.assertRaises(self.client_mod.APIError):
                self.client.wait_for_checkout("s", timeout=0.01, poll_interval=0)


class ConfigTest(unittest.TestCase):
    def setUp(self):
        load_plugin()
        from aimlapi import config

        self.config = config

    def test_trusted_hosts(self):
        trusted = self.config.is_trusted_aimlapi_url
        self.assertTrue(trusted("https://api.aimlapi.com/v1"))
        self.assertTrue(trusted("https://aimlapi.com/app"))
        self.assertFalse(trusted("http://api.aimlapi.com/v1"))
        self.assertFalse(trusted("https://aimlapi.com.evil.example"))
        self.assertFalse(trusted("https://user:pw@api.aimlapi.com"))

    def test_attribution_is_off_unless_opted_in(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.config.attribution_headers(), {})
        with mock.patch.dict(os.environ, {"AIMLAPI_ATTRIBUTION": "0"}, clear=True):
            self.assertEqual(self.config.attribution_headers(), {})
        with mock.patch.dict(os.environ, {"AIMLAPI_ATTRIBUTION": "1"}, clear=True):
            self.assertEqual(
                set(self.config.attribution_headers()),
                {"X-AIMLAPI-Source", "X-AIMLAPI-Partner-ID", "X-AIMLAPI-Integration-Repo",
                 "X-AIMLAPI-Integration-Version"},
            )

    def test_checkout_return_urls_quote_the_session_token(self):
        success, cancel = self.config.build_checkout_return_urls("a/b c")
        self.assertEqual(
            success, "https://pay.aimlapi.com/checkout?checkout=success&partnerCheckout=1&sessionToken=a%2Fb%20c"
        )
        self.assertTrue(cancel.startswith("https://pay.aimlapi.com/checkout?checkout=cancel&"))


if __name__ == "__main__":
    unittest.main()
