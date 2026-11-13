# hermes-provider-aimlapi

[aimlapi.com](https://aimlapi.com) model-provider plugin for
[Hermes Agent](https://github.com/NousResearch/hermes-agent), maintained by aimlapi.com.

AI/ML API provides access to **10,000+ models and MCP tools** through one account.
The plugin registers `aimlapi` as an OpenAI-compatible chat provider at
`https://api.aimlapi.com/v1`, with models from OpenAI, Anthropic, Google,
DeepSeek, Qwen, Moonshot, xAI and others. Its optional MCP connection adds
model discovery, media generation and the AI/ML API Toolbox; the combined
count covers models and tools, not chat models alone.
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

## aimlapi.com MCP server (optional, off by default)

The aimlapi.com MCP server (`https://mcp.aimlapi.com/mcp`) gives the agent
tools for model discovery, account balance and usage, image/video/audio
generation, chat, embeddings, OCR and the aimlapi.com Toolbox
(`tools_search` → `tools_inspect` → `tools_run`). Generation, chat and
Toolbox runs are billed to your aimlapi.com balance, so the plugin never adds
it on its own.

At the end of the guided `hermes model` step (builds with
`model_setup_flow`) the plugin asks:

```text
Add the aimlapi.com MCP server to Hermes? [y/N]
```

Enter, `n`, Ctrl+C or a closed stdin all mean no. On `y` it adds this to your
`config.yaml` (an existing `mcp_servers.aimlapi` entry is never changed):

```yaml
mcp_servers:
  aimlapi:
    url: https://mcp.aimlapi.com/mcp
    headers:
      Authorization: Bearer ${AIMLAPI_API_KEY}
    trust: untrusted
```

- `${AIMLAPI_API_KEY}` is resolved by Hermes when it connects, from your
  Hermes `.env`; the key itself is not written to `config.yaml`.
- `trust: untrusted` makes Hermes ask before every tool call the server does
  not mark read-only (every billed call). Read-only tools such as `ping`,
  `models_search` or `account_balance` run without a prompt.
- If the aimlapi.com provider points anywhere other than
  `https://api.aimlapi.com` (a proxy or gateway via `AIMLAPI_INFERENCE_URL`
  or `model.base_url`), `AIMLAPI_API_KEY` may be that endpoint's key, so the
  entry gets `auth: oauth` and no key; sign in with
  `hermes mcp login aimlapi`.
- With `AIMLAPI_ATTRIBUTION=1` at that moment the entry also carries the
  attribution headers described below (`X-AIMLAPI-Source`,
  `X-AIMLAPI-Partner-ID`, ...), only ever for the exact host `mcp.aimlapi.com`.

The tools load in your next session (`hermes mcp list`, `hermes mcp test aimlapi`).
To remove it: `hermes mcp remove aimlapi`.

On builds without `model_setup_flow`, add the same block to `config.yaml` by
hand (keep the `${AIMLAPI_API_KEY}` reference as written). Only do this when
`AIMLAPI_API_KEY` is an aimlapi.com key; otherwise drop `headers` and use
`auth: oauth`.

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
- **The optional MCP server** (only after you answer yes, see above) is reached
  at `mcp.aimlapi.com` with `Authorization: Bearer ${AIMLAPI_API_KEY}`, or
  through OAuth when the provider points at a non-aimlapi.com endpoint.
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

`tests/hermes_e2e_setup.py` and `tests/hermes_e2e_mcp.py` drive the `hermes
model` step inside a real Hermes checkout (see the CI workflow for how).

The unit tests run against stub Hermes modules, offline. CI also checks out
Hermes Agent (latest release and `main`), runs
`hermes plugins validate --install-deps aimlapi` and loads the plugin through
real provider discovery (`tests/hermes_smoke.py`).

## License

MIT — see [LICENSE](LICENSE).
