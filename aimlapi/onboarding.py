"""Interactive aimlapi.com key acquisition for the ``hermes model`` step.

Terminal output goes through ``hermes_cli.cli_output``; input is read with
``hermes_cli.cli_output.line_input`` (``getpass`` for the API key), so Ctrl+C
or EOF at any prompt ends the step without saving anything.
"""

from __future__ import annotations

import getpass
import math
import os
import re
import sys
import time
import webbrowser

from .client import APIError, AimlapiClient
from .config import (
    DEFAULT_AMOUNT_USD_MINOR,
    MAX_AMOUNT_USD_MINOR,
    MIN_AMOUNT_USD_MINOR,
    resolve_endpoints,
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CODE_RE = re.compile(r"\d{6}")


class _Cancelled(Exception):
    """The user pressed Ctrl+C or closed stdin at a prompt."""


def _out():
    from hermes_cli import cli_output

    return cli_output


def _read(label: str) -> str:
    try:
        return _out().line_input(f"  {label}").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        raise _Cancelled from None


def _read_secret(label: str) -> str:
    try:
        return getpass.getpass(f"  {label}").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        raise _Cancelled from None


def _debug(stage: str, error: Exception) -> None:
    if os.getenv("AIMLAPI_DEBUG", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    print(f"  [aimlapi.com debug] {stage}: {error}", file=sys.stderr)


def _retry_idempotent(call):
    retry_delays = (1.0, 2.0, 4.0, 8.0)
    for attempt in range(len(retry_delays) + 1):
        try:
            return call()
        except APIError as exc:
            retryable = exc.status == 404 or not exc.status or exc.status >= 500
            if not retryable or attempt == len(retry_delays):
                raise
            time.sleep(retry_delays[attempt])
    raise RuntimeError("unreachable")


def _prompt_choice(title: str, labels: list[str], default: int = 0) -> int:
    print()
    _out().print_header(title)
    for index, label in enumerate(labels, start=1):
        print(f"    {index}. {label}")
    while True:
        raw = _read(f"Choice [{default + 1}]: ")
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(labels):
            return int(raw) - 1
        _out().print_error(f"Please enter a number from 1 to {len(labels)}.")


def _prompt_amount() -> int:
    default_usd = DEFAULT_AMOUNT_USD_MINOR / 100
    minimum = MIN_AMOUNT_USD_MINOR / 100
    maximum = MAX_AMOUNT_USD_MINOR / 100
    print()
    _out().print_header(f"Add credits (min ${minimum:.0f}).")
    while True:
        raw = _read(f"Amount in USD [{default_usd:.0f}]: ")
        try:
            amount = float(raw) if raw else default_usd
        except ValueError:
            amount = math.nan
        if not math.isfinite(amount):
            _out().print_error("Please enter a top-up amount.")
            continue
        minor = round(amount * 100)
        if minor < MIN_AMOUNT_USD_MINOR:
            _out().print_error(f"Minimum top-up is ${minimum:.0f}.")
            continue
        if minor > MAX_AMOUNT_USD_MINOR:
            _out().print_error(f"Maximum top-up is ${maximum:.0f}.")
            continue
        return minor


def _open_and_wait(client: AimlapiClient, session_token: str, checkout_url: str) -> str:
    print()
    _out().print_warning("Opening checkout in your browser...")
    print("  If the browser did not open, use this link to top up your account:")
    print()
    print(f"  {checkout_url}")
    print()
    try:
        webbrowser.open(checkout_url)
    except Exception:  # no usable browser: the printed link is the fallback
        pass
    print("  Waiting for payment confirmation. Press Ctrl+C to cancel.")
    try:
        return client.wait_for_checkout(session_token)
    except KeyboardInterrupt:
        print()
        raise _Cancelled from None


def _paste_existing_key(client: AimlapiClient) -> str:
    while True:
        print()
        api_key = _read_secret("Paste your aimlapi.com key: ")
        if not api_key:
            _out().print_error("Please paste a valid aimlapi.com key.")
            continue
        try:
            client.validate_api_key(api_key)
        except APIError as exc:
            _debug("validating pasted API key", exc)
            if exc.status in {401, 403}:
                _out().print_error("The aimlapi.com key is invalid or revoked. Please try again.")
            else:
                _out().print_error("The aimlapi.com key could not be validated. Please try again.")
            continue
        return api_key


def _read_email() -> str:
    print()
    while True:
        email = _read("Email: ").lower()
        if _EMAIL_RE.fullmatch(email):
            return email
        _out().print_error("Email format is incorrect. Please try again.")


def guided_api_key_setup(existing_key: str = "") -> str | None:
    """Return a working aimlapi.com API key, or None when the user stops."""
    stage = "starting guided setup"
    try:
        if existing_key.strip():
            keep = _prompt_choice(
                "aimlapi.com account is already configured",
                ["Continue with your saved API key", "Set up a new key or switch account"],
            )
            if keep == 0:
                _out().print_success("Everything is ready.")
                return existing_key.strip()

        client = AimlapiClient(resolve_endpoints())
        has_key = _prompt_choice(
            "Do you have an aimlapi.com key?",
            ["I am a new user", "I already have an aimlapi.com key"],
        )
        if has_key == 1:
            api_key = _paste_existing_key(client)
            _out().print_success("Everything is ready.")
            return api_key

        email = _read_email()
        stage = "checking account"
        action = client.check_account(email)
        if action == "sign-in":
            stage = "sending sign-in code"
            client.send_sign_in_code(email)
            code = _read(f"Enter the 6-digit code sent to {email}: ")
            if not _CODE_RE.fullmatch(code):
                _out().print_error("Code is incorrect.")
                return None
            stage = "verifying sign-in code"
            bearer = client.verify_sign_in_code(email, code)
            stage = "creating API key"
            api_key = client.create_key(bearer)
        else:
            stage = "creating passwordless account"
            bearer = client.create_passwordless_account(email)
            amount = _prompt_amount()
            auto_top_up = _prompt_choice("Auto top-up.", ["On", "Off"]) == 0
            stage = "creating checkout session"
            session_token = client.create_checkout_session()
            payment_session_id = client.new_payment_session_id()
            stage = "starting checkout"
            checkout_url = _retry_idempotent(
                lambda: client.start_checkout(
                    bearer,
                    session_token,
                    amount,
                    payment_session_id,
                    auto_top_up,
                )
            )
            stage = "waiting for checkout"
            paid_session_token = _open_and_wait(client, session_token, checkout_url)
            stage = "exchanging checkout for API key"
            api_key = client.exchange_checkout(bearer, paid_session_token)
            print()
            _out().print_success(
                f"Top-up successful - ${amount / 100:.0f} credited to your account"
            )
            print(f"  We've emailed you a magic link to {email}.")
            print("  Use it to access your aimlapi.com account and review your usage.")

        print()
        _out().print_success("Everything is ready.")
        return api_key
    except _Cancelled:
        return None
    except (APIError, ValueError) as exc:
        _debug(stage, exc)
        _out().print_error("Sign in failed, please try again.")
        return None
