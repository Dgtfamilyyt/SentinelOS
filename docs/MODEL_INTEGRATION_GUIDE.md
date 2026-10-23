# SentinelOS Model Integration & Future Activation Guide

## 1. Overview & Architecture

SentinelOS is designed with strict decoupling between:
1. **Frontend Interface (`c:\sentinelOS-interface`)**: Web UI and Node.js proxy server.
2. **SentinelOS Backend Daemon (`c:\SentinelOS`)**: FastAPI server and core command engine.
3. **Model Runtime Engine**: Local runtime (e.g., Ollama daemon) or remote proxy (OmniRoute).
4. **AI Models & Weights**: Actual LLM parameter weights on disk.
5. **Tools & Additional Services**: Deterministic tools (nmap, nikto, whois, system monitor, molecular lab) that function independently of AI model availability.

### Decoupled State Matrix

| Component | Monitored States | Notes |
| :--- | :--- | :--- |
| **Frontend** | `running`, `stopped` | Express + Vite server (`:3000`) |
| **Backend Daemon** | `connected`, `disconnected` | FastAPI core daemon (`:8000/api/health`) |
| **Model Runtime** | `available`, `unavailable`, `not_configured` | Probed via provider `check_runtime()` (`:8000/api/models/status`) |
| **AI Model Inventory** | `ready`, `loading`, `unavailable`, `not_configured` | Real inventory from runtime (`:8000/api/models`) |
| **Tools & Services** | Real individual status | Independent execution (`/status`, `/targets`, etc.) |

An unavailable or unconfigured AI model **never breaks the dashboard, interface, or deterministic tools**.

---

## 2. Model Provider Integration Layer

The SentinelOS model integration layer lives in `models/provider.py` and delegates through `models/router.py`:

```
                    +---------------------------+
                    |  SentinelOS Web Interface |
                    +-------------+-------------+
                                  |
                                  v
                    +---------------------------+
                    | SentinelOS FastAPI Backend|
                    |       (:8000/api)         |
                    +-------------+-------------+
                                  |
                      +-----------v-----------+
                      |   models.router       |
                      |   (ModelRouter)       |
                      +-----------+-----------+
                                  |
         +------------------------+------------------------+
         |                                                 |
+--------v----------+                             +--------v----------+
|  OllamaProvider   |                             | OmniRouteProvider |
| (Local Runtime)   |                             | (Remote/Federated)|
+-------------------+                             +-------------------+
         |                                                 |
         v                                                 v
  Ollama Daemon                                    OmniRoute Proxy
  (http://127.0.0.1:11434)                         (http://127.0.0.1:20128)
```

### Key Provider Methods

- `check_runtime() -> ProviderRuntimeStatus`: Non-blocking HTTP check of the runtime daemon.
- `list_models() -> list[ModelInventoryItem]`: Queries actual installed models. **Returns an empty list if none are installed; never invents fake models.**
- `get_model_status(model_id) -> str`: Checks readiness (`ready`, `loading`, `unavailable`, `not_configured`).
- `generate(model, messages, **kwargs) -> str`: Chat completion via runtime API.
- `stream(model, messages, **kwargs)`: Async token generator.

---

## 3. Step-by-Step Activation Workflow

When you are ready to install and activate an AI model, follow these **6 steps**:

### Step 1: Install or Configure the Chosen Model Runtime
Install your chosen runtime (for example, Ollama):
- **Ollama**: Download and install from the official distribution for your OS.
- Start the daemon:
  ```powershell
  # Default address: http://127.0.0.1:11434
  ollama serve
  ```
- Pull or load your desired model:
  ```powershell
  ollama pull qwen2.5:3b
  # or whichever compatible model you choose
  ```

### Step 2: Configure the Backend Provider in `.env`
Copy `.env.example` to `.env` in `c:\SentinelOS`:
```ini
SENTINEL_WORKSPACE_ROOT="./workspace"
OLLAMA_HOST="http://127.0.0.1:11434"
SENTINEL_AI_BACKEND="local"
```
If using OmniRoute:
```ini
SENTINEL_AI_BACKEND="omniroute"
SENTINEL_OMNIROUTE_ENABLED="true"
SENTINEL_OMNIROUTE_BASE_URL="http://127.0.0.1:20128/v1"
```

### Step 3: Verify Runtime and Model Availability
Verify using the SentinelOS backend API:
```powershell
# 1. Check runtime and model status
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/models/status"

# Expected JSON when models are installed:
# {
#   "runtime_status": "available",
#   "model_status": "ready",
#   "models_count": 1,
#   "provider": "ollama",
#   "active_model": "qwen2.5:3b",
#   "message": "1 model(s) available."
# }

# 2. Check installed inventory
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/models"
```

### Step 4: Connect the Model to the Router
Assign the model to a task role via the API or Model Hub UI:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/models/select" `
  -Method POST `
  -Headers @{ "Content-Type" = "application/json" } `
  -Body '{"model": "qwen2.5:3b", "role": "general"}'
```
Or open the **Model Hub (View 08)** in the web interface and click **Assign Role**.

### Step 5: Run a Real Chat Test Through the Frontend
1. Open the web interface at `http://localhost:3000`.
2. Go to the **Command Center (View 01)** or **Ultron Core**.
3. Send a test prompt:
   ```text
   What is your status?
   ```
4. Verify that the backend routes the prompt to the configured model.

### Step 6: Confirm the Response Came from the Intended Model
- Verify in SentinelOS logs (`c:\SentinelOS\logs\sentinel.log` or console output) that the model provider received and completed the prompt.
- Confirm the response content reflects actual AI output rather than a static fallback or mock string.

---

## 4. Current Safe State Verification (No Models Required)

You can verify that the system is fully operational today without downloading any models:

1. **Backend Tests:**
   ```powershell
   c:\SentinelOS\.venv\Scripts\pytest.exe c:\SentinelOS
   # 200 passed
   ```

2. **Frontend Build & Linter:**
   ```powershell
   cd c:\sentinelOS-interface
   npm.cmd run lint
   npm.cmd run build
   ```

3. **Runtime Decoupling Verification:**
   - When Ollama is stopped, the backend reports:
     - `runtime_status`: `"unavailable"`
     - `model_status`: `"unavailable"`
     - Header badge shows: `AI: UNAVAILABLE` (Amber/Orange badge)
     - Backend status badge shows: `BACKEND: ONLINE` (Green badge)
   - When Ollama is running but has no models:
     - `runtime_status`: `"available"`
     - `model_status`: `"not_configured"`
     - Header badge shows: `AI: NOT CONFIGURED` (Amber badge)
     - Model Hub shows: `AI models not configured yet` with empty inventory and setup instructions.
     - Sending a prompt returns an honest 503 HTTP notice:
       `"AI models not configured yet. AI responses are unavailable until a compatible model is installed in your runtime."`
     - Deterministic commands (`/status`, `/targets`, etc.) execute immediately with full tool results.
