import unittest
from unittest import mock

from stubs import load_plugin


class FakeClient:
    """Scripted stand-in for ``AimlapiClient``; records the calls it receives."""

    def __init__(self, action="sign-up", valid_keys=("good-key",)):
        self.action = action
        self.valid_keys = set(valid_keys)
        self.calls = []

    def _call(self, name, *args):
        self.calls.append((name,) + args)

    def validate_api_key(self, key):
        self._call("validate_api_key", key)
        if key not in self.valid_keys:
            from aimlapi.client import APIError

            raise APIError("rejected", status=401)

    def check_account(self, email):
        self._call("check_account", email)
        return self.action

    def send_sign_in_code(self, email):
        self._call("send_sign_in_code", email)

    def verify_sign_in_code(self, email, code):
        self._call("verify_sign_in_code", email, code)
        return "bearer"

    def create_key(self, bearer):
        self._call("create_key", bearer)
        return "signed-in-key"

    def create_passwordless_account(self, email):
        self._call("create_passwordless_account", email)
        return "bearer"

    def create_checkout_session(self):
        self._call("create_checkout_session")
        return "session"

    def new_payment_session_id(self):
        return "payment-id"

    def start_checkout(self, bearer, session, amount, payment_id, auto_top_up):
        self._call("start_checkout", bearer, session, amount, payment_id, auto_top_up)
        return "https://checkout.stripe.com/c/pay"

    def wait_for_checkout(self, session):
        self._call("wait_for_checkout", session)
        return "paid-session"

    def exchange_checkout(self, bearer, session):
        self._call("exchange_checkout", bearer, session)
        return "new-account-key"


class GuidedSetupTest(unittest.TestCase):
    def setUp(self):
        _, self.rec = load_plugin()
        from aimlapi import onboarding

        self.onboarding = onboarding
        self.fake = FakeClient()
        patcher = mock.patch.object(onboarding, "AimlapiClient", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _names(self):
        return [call[0] for call in self.fake.calls]

    def test_keeps_the_saved_key(self):
        self.rec.answer("1")
        self.assertEqual(self.onboarding.guided_api_key_setup("saved-key"), "saved-key")
        self.assertEqual(self.fake.calls, [])

    def test_pasted_key_is_validated_until_it_works(self):
        self.rec.answer("2")
        with mock.patch("getpass.getpass", side_effect=["bad-key", "good-key"]):
            self.assertEqual(self.onboarding.guided_api_key_setup(), "good-key")
        self.assertEqual(self._names(), ["validate_api_key", "validate_api_key"])

    def test_new_user_signs_up_tops_up_and_gets_a_key(self):
        self.rec.answer("", "not-an-email", "New@Example.com", "30", "2")
        with mock.patch("webbrowser.open") as browser:
            self.assertEqual(self.onboarding.guided_api_key_setup(), "new-account-key")
        browser.assert_called_once_with("https://checkout.stripe.com/c/pay")
        self.assertEqual(
            self._names(),
            ["check_account", "create_passwordless_account", "create_checkout_session",
             "start_checkout", "wait_for_checkout", "exchange_checkout"],
        )
        self.assertIn(("check_account", "new@example.com"), self.fake.calls)
        self.assertIn(("start_checkout", "bearer", "session", 3000, "payment-id", False), self.fake.calls)
        self.assertIn(("exchange_checkout", "bearer", "paid-session"), self.fake.calls)

    def test_top_up_amount_is_bounded(self):
        self.rec.answer("", "a@b.co", "5", "abc", "25", "1")
        with mock.patch("webbrowser.open"):
            self.onboarding.guided_api_key_setup()
        self.assertIn(("start_checkout", "bearer", "session", 2500, "payment-id", True), self.fake.calls)
        errors = [line for line in self.rec.output if line.startswith("error: ")]
        self.assertEqual(errors, ["error: Minimum top-up is $20.", "error: Please enter a top-up amount."])

    def test_existing_account_signs_in_with_a_code(self):
        self.fake.action = "sign-in"
        self.rec.answer("", "a@b.co", "123456")
        self.assertEqual(self.onboarding.guided_api_key_setup(), "signed-in-key")
        self.assertEqual(
            self._names(), ["check_account", "send_sign_in_code", "verify_sign_in_code", "create_key"]
        )

    def test_malformed_code_stops_without_a_key(self):
        self.fake.action = "sign-in"
        self.rec.answer("", "a@b.co", "12ab")
        self.assertIsNone(self.onboarding.guided_api_key_setup())
        self.assertNotIn("verify_sign_in_code", self._names())

    def test_ctrl_c_at_any_prompt_returns_none(self):
        self.rec.answer("", KeyboardInterrupt())
        self.assertIsNone(self.onboarding.guided_api_key_setup())
        self.assertEqual(self.fake.calls, [])

    def test_api_failure_is_reported_not_raised(self):
        from aimlapi.client import APIError

        self.rec.answer("", "a@b.co")
        with mock.patch.object(self.fake, "check_account", side_effect=APIError("down", status=503)):
            self.assertIsNone(self.onboarding.guided_api_key_setup())
        self.assertIn("error: Sign in failed, please try again.", self.rec.output)


if __name__ == "__main__":
    unittest.main()
