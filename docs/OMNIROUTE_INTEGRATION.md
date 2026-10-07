# OmniRoute model backend

SentinelOS remains the agent: CommandCenter and Planner choose work, AIEngine
prepares prompts, and ToolManager independently validates and executes tools.
OmniRoute is an optional OpenAI-compatible model transport behind
`models.router.ModelRouter`; the cloned service is not imported by SentinelOS.

```text
User → CommandCenter → Planner → AIEngine → ModelRouter
                                           ├─ LocalBackend → Ollama
                                           └─ OmniRouteBackend → OmniRoute → provider/model
      ← response ← verification/state ← SentinelOS ←──────────────┘
                         ToolManager → policy → validation → execution
```

## Configuration

SentinelOS reads its existing process environment; it does not require a second
configuration file. Local Ollama remains the default and requires no provider
credentials. To opt in to OmniRoute, start the cloned OmniRoute service
separately (see `OmniRoute/README.md`) and set:

```text
SENTINEL_AI_BACKEND=auto
SENTINEL_OMNIROUTE_ENABLED=true
SENTINEL_OMNIROUTE_BASE_URL=http://127.0.0.1:20128/v1
SENTINEL_OMNIROUTE_API_KEY=<optional inbound OmniRoute API key>
SENTINEL_OMNIROUTE_MODELS={"chat":"provider/model-id","planning":"provider/model-id","red":"provider/model-id"}
SENTINEL_OMNIROUTE_FALLBACK_TO_LOCAL=true
SENTINEL_OMNIROUTE_DATA_POLICY=redact
```

Put credentials in the environment or the existing secret manager; never commit
them. Remote model IDs are an explicit allowlist in `SENTINEL_OMNIROUTE_MODELS`.
Sentinel's four registered local models remain accepted; additional local model
selections are checked against Ollama's installed-model list before use.
Use `SENTINEL_AI_BACKEND=local` to force Ollama, `omniroute` to require the
configured remote route, or `auto` to use OmniRoute only for enabled tasks with
a configured remote model. In `auto`, an unconfigured task remains local.

OmniRoute fallback is enabled by default and can be disabled with
`SENTINEL_OMNIROUTE_FALLBACK_TO_LOCAL=false`. When enabled, Sentinel logs the
remote failure category and fallback outcome. With fallback disabled, callers
receive a safe structured error. Invalid settings also produce a structured
configuration error and do not prevent SentinelOS from starting.

Remote data policy defaults to `redact`, which removes common credential forms
and local absolute paths from message text before transmission. `deny` blocks
remote requests. `allow` explicitly permits the configured remote provider to
receive message contents as supplied. Environment variables and API credentials
are never added to model messages; the OmniRoute API key is sent only in its
HTTP Authorization header. These settings do not grant a model tool execution
authority.

The adapter sends only OpenAI-compatible `/chat/completions` requests with
`trust_env=False`; network proxies from the host environment are not used. URL
configuration permits HTTPS, or HTTP to loopback only. OmniRoute provider
credentials stay in OmniRoute's own configuration. The local model registry and
its Ollama IDs are unchanged.

## Diagnostics and tests

`GET /api/health` includes an `omniroute` object with installation, enablement,
configuration, endpoint, provider/model availability, and status fields. It is
diagnostic only; an OmniRoute health failure never prevents local startup.
`GET /api/models` continues to list Ollama models and includes configured remote
models only when OmniRoute reports them available.

Run the adapter and routing tests with:

```powershell
python -m pytest -v tests/test_omniroute.py tests/test_router.py tests/test_streaming.py tests/test_api.py
```

Run the full SentinelOS suite with `python -m pytest -v`.
