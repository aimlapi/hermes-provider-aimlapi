# hermes-provider-aimlapi

[aimlapi.com](https://aimlapi.com) model-provider plugin for
[Hermes Agent](https://github.com/NousResearch/hermes-agent), maintained by aimlapi.com.

It registers aimlapi.com as the `aimlapi` provider over the OpenAI-compatible
Chat Completions endpoint `https://api.aimlapi.com/v1`: one key for 1000+
models from OpenAI, Anthropic, Google, DeepSeek, Qwen, Moonshot, xAI and others.
Credential resolution, the `/model` picker, `hermes doctor` and `--provider`
auto-wire from the Hermes provider registry. The plugin touches no Hermes core
files.

## Install

```bash
hermes plugins install aimlapi
```

Or drop it in by hand (works on any build with model-provider plugins):

```bash
git clone https://github.com/aimlapi/hermes-provider-aimlapi.git
mkdir -p ~/.hermes/plugins/model-providers
cp -r hermes-provider-aimlapi/aimlapi ~/.hermes/plugins/model-providers/aimlapi
```

Or as a pip entry point (`pip install git+https://github.com/aimlapi/hermes-provider-aimlapi.git`,
then `hermes plugins enable aimlapi`).

## Set up

```bash
hermes model        # pick aimlapi.com
```

On Hermes builds whose `ProviderProfile` has `model_setup_flow` (Hermes `main`
today), the aimlapi.com step is guided:

1. **Already have a key?** Paste it; the plugin checks it against
   `https://api.aimlapi.com/v2/billing` before saving.
2. **New user?** Enter your email, choose a top-up amount ($20 minimum, $25 by
   default) and whether to turn on auto top-up. Hermes opens the aimlapi.com /
   Stripe checkout in your browser and waits for the payment (Ctrl+C cancels).
   The issued key is saved, and aimlapi.com emails you a magic link to the
   account dashboard.
3. **Email already has an account?** aimlapi.com sends a 6-digit code instead;
   after you enter it the plugin creates a key named "Hermes Agent".

If a saved key is found, the step first asks whether to keep it.

The key is saved through Hermes (`AIMLAPI_API_KEY` in `~/.hermes/.env`). Then
the model picker opens with the hottest models first, every other tool-capable
chat model after them, and live input/output prices.

On builds without `model_setup_flow` (0.22.x releases), `hermes model` runs the
generic API-key prompt instead. You can always set the key yourself:

```bash
export AIMLAPI_API_KEY=...   # get one at https://aimlapi.com/app/keys
hermes --provider aimlapi --model anthropic/claude-sonnet-5
```

The guided step needs an interactive terminal. Under cron, the messaging
gateway or a redirected stdin it prints how to set `AIMLAPI_API_KEY` and stops.

## Models

The picker reads `https://api.aimlapi.com/v1/models?include=capabilities,pricing`
(no key needed) and keeps chat models that support tool calling, plus the
models aimlapi.com marks as hottest. When the catalog is unreachable a curated
fallback list is shown. Auxiliary tasks default to `anthropic/claude-sonnet-5`.

## What the plugin sends where

- **Model requests** (your prompts) go to `api.aimlapi.com` with your
  `AIMLAPI_API_KEY`, like any other provider.
- **The model catalog** is fetched from `api.aimlapi.com` without a key.
- **Guided setup only** talks to `auth.aimlapi.com`, `app.aimlapi.com` and
  `api.aimlapi.com`: your email, the 6-digit code, the top-up amount and the
  auto top-up choice. A new-account checkout is created as an aimlapi.com
  partner checkout carrying the partner id for this integration
  (`part_H9mK4xR7vT2qN8pL5cY3wBfD`, name `hermes-agent`). Payment happens on
  the aimlapi.com / Stripe checkout page in your browser; card details never
  pass through Hermes or this plugin.
- **Attribution headers are off by default.** With `AIMLAPI_ATTRIBUTION=1`,
  requests to `*.aimlapi.com` also carry `X-AIMLAPI-Source`,
  `X-AIMLAPI-Partner-ID`, `X-AIMLAPI-Integration-Repo` and
  `X-AIMLAPI-Integration-Version`, which credit the traffic to this
  integration in aimlapi.com's partner program. They never go to other hosts.

The plugin has no dependencies beyond the Python standard library, runs no
shell commands, starts no background processes and does not update itself.

## Environment variables

| Variable | Purpose |
|---|---|
| `AIMLAPI_API_KEY` | Your aimlapi.com key (required) |
| `AIMLAPI_ATTRIBUTION` | `1` to send the attribution headers above (off by default) |
| `AIMLAPI_DEBUG` | `1` to print the failing step of the guided setup |
| `AIMLAPI_INVITE_CODE` | Invite code applied to a new account |
| `AIMLAPI_INFERENCE_URL`, `AIMLAPI_AUTH_URL`, `AIMLAPI_APP_URL`, `AIMLAPI_PAY_URL`, `AIMLAPI_VERIFICATION_BASE_URL`, `AIMLAPI_RETURN_URL` | Staging endpoint overrides for aimlapi.com developers; the setup endpoints must be HTTPS on `aimlapi.com` |
| `AIMLAPI_PARTNER_ID` | Overrides the partner id (aimlapi.com developers) |

## Development

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The unit tests run against stub Hermes modules, offline. CI also checks out
Hermes Agent (latest release and `main`), runs
`hermes plugins validate --install-deps aimlapi` and loads the plugin through
real provider discovery (`tests/hermes_smoke.py`).

## License

MIT — see [LICENSE](LICENSE).
