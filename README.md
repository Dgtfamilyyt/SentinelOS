# 🛡️ Sentinel OS

> **A local-first, multi-model AI operating system for Red Team, SOC, Purple Team, software engineering, and security research.**

**Sentinel OS** is an experimental local AI platform designed to combine large language models, autonomous tool selection, secure tool execution, memory, and cybersecurity workflows behind a single assistant.

Instead of relying on one model for everything, Sentinel routes different tasks to specialized local models and exposes capabilities through a modular Tool SDK.

The long-term objective is simple:

> **Build one AI that can think like a Red Teamer, investigate like a SOC analyst, correlate both sides like a Purple Teamer, and operate through extensible local tools.**

---

## 🚧 Project Status

**Stage:** Alpha / Active Development

Sentinel OS is currently under heavy development.

### Working

* ✅ Local Ollama integration
* ✅ Multi-model architecture
* ✅ Model registry
* ✅ Model router
* ✅ General / Coding / Red / SOC / Purple task routing
* ✅ AI planning layer
* ✅ Central AI client
* ✅ Command Center
* ✅ Dispatcher
* ✅ Tool SDK
* ✅ Automatic tool discovery
* ✅ Tool validation
* ✅ Tool registry
* ✅ Tool execution
* ✅ Parameter validation
* ✅ Filesystem workspace sandbox
* ✅ Conversation support
* ✅ SQLite-based persistent memory foundation
* ✅ Logging
* ✅ Pytest test suite
* ✅ Local FastAPI interface
* ✅ Voice-capable browser command console

### In Development

* 🚧 Red Team capability pack
* 🚧 SOC analysis tools
* 🚧 Purple Team correlation
* 🚧 Tool permission engine
* 🚧 Tool-result reasoning
* 🚧 Semantic long-term memory
* 🚧 Plugin loader
* 🚧 Advanced security dashboard

---

# 🧠 Core Idea

Traditional local AI applications usually follow:

```text
User
 ↓
One LLM
 ↓
Answer
```

Sentinel is designed differently:

```text
                     USER
                      │
                      ▼
                Command Center
                      │
                      ▼
                   Planner
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
      CHAT          CODING       SECURITY
                                    │
                       ┌────────────┼────────────┐
                       ▼            ▼            ▼
                     🔴 RED       🔵 SOC       🟣 PURPLE
                       │            │            │
                       └────────────┼────────────┘
                                    ▼
                               Dispatcher
                              /          \
                             ▼            ▼
                       Tool Manager     AI Engine
                             │             │
                        Validator      Model Router
                             │             │
                         Workspace      AI Client
                             │             │
                           Tools         Ollama
```

The AI decides.

The operating layer executes.

---

# 🔴 Red Team

Sentinel's Red Team mode is intended for authorized security research, labs, CTFs, penetration testing, vulnerability assessment, and offensive-security analysis.

Planned areas include:

* Reconnaissance analysis
* Service enumeration
* Network security
* Web security testing
* Attack-surface analysis
* Vulnerability analysis
* Exploit research
* Linux security
* Evidence parsing
* Security report generation

Sentinel should reason from evidence rather than claim that an exploit, command, or test succeeded without actual tool output.

---

# 🔵 SOC / Blue Team

SOC mode is designed to approach security problems from the defender's perspective.

Planned capabilities include:

* Alert triage
* Authentication analysis
* Log analysis
* IOC extraction
* Threat hunting
* Incident investigation
* Network telemetry analysis
* Process activity analysis
* Incident timeline generation
* Detection engineering
* Severity and confidence estimation

Example future workflow:

```text
Security Logs
     ↓
Sentinel
     ↓
Event Normalization
     ↓
Timeline
     ↓
Suspicious Activity
     ↓
Investigation Guidance
```

---

# 🟣 Purple Team

Purple Team mode connects offensive activity with defensive visibility.

Instead of asking only:

> How does this attack work?

Sentinel should also ask:

> What telemetry would this generate?

> Would the SOC detect it?

> Where is the detection gap?

The target workflow is:

```text
Red Team Technique
       ↓
Expected Telemetry
       ↓
SOC Detection
       ↓
Detection Gap
       ↓
Rule Improvement
       ↓
Retest
```

This Red ↔ Blue feedback loop is intended to become one of Sentinel OS's defining capabilities.

---

# 🤖 Multi-Model Intelligence

Sentinel does not rely on one giant model for every request.

Current local model roles:

| Role                 | Model                                                        |
| -------------------- | ------------------------------------------------------------ |
| 💬 General           | `qwen3:4b`                                                   |
| 💻 Coding / Planning | `WhiteRabbitNeo/WhiteRabbitNeo-2.5-Qwen-2.5-Coder-7B:latest` |
| 🛡️ Cybersecurity    | `CyberCrew/notmythos-8b:latest`                              |
| 🧠 Deep Reasoning    | `qwen3.6:latest`                                             |

Example:

```text
"Hey Sentinel"
       ↓
Qwen3 4B
```

```text
"Debug this Python traceback"
       ↓
WhiteRabbitNeo
```

```text
"Analyze these exposed services from my pentest"
       ↓
NotMythos
```

```text
"Perform deep architectural reasoning"
       ↓
Qwen3.6
```

The user interacts with **Sentinel**.

The Model Router decides which underlying model should handle the task.

---

# ⚡ Planner

Before responding, Sentinel's Planner classifies the request.

Current task classes include:

```text
chat
coding
red
soc
purple
cyber
```

A request can become:

```json
{
  "type": "chat",
  "task": "soc"
}
```

or a tool request:

```json
{
  "type": "tool",
  "task": "red",
  "tool": "read_file",
  "parameters": {
    "filename": "scan.txt"
  }
}
```

The Planner is not allowed to execute tools directly.

Execution is handled separately by Sentinel's Dispatcher and Tool Manager.

---

# 🔧 Tool SDK

Sentinel uses a self-discovering Tool SDK.

A tool only needs to inherit from the base `Tool` class:

```python
from tools.base import Tool


class ExampleTool(Tool):

    name = "example_tool"

    description = "Example Sentinel capability."

    category = "example"

    parameters = {}

    def execute(self, **kwargs):
        return "Hello from Sentinel."
```

Sentinel automatically scans tool modules, discovers valid Tool subclasses, validates them, and registers them.

No central list of hundreds of tools is required.

---

# 🔍 Automatic Tool Discovery

The Tool Manager scans the tool packages automatically:

```text
tools/
   ↓
Discover modules
   ↓
Inspect classes
   ↓
Find Tool subclasses
   ↓
Validate
   ↓
Register
```

This allows Sentinel to scale without adding giant collections of:

```python
if tool == "..."
```

statements.

---

# 🔐 Workspace Sandbox

AI-facing filesystem tools operate inside a configured workspace.

Default:

```text
SentinelOS/
└── workspace/
```

Allowed:

```text
workspace/report.txt
workspace/logs/auth.log
workspace/project/
```

Rejected:

```text
../README.md
../../Windows/System32
C:\Users\...
```

Paths are resolved before execution and attempts to escape the configured workspace are rejected.

The design principle is:

> **Broad reasoning. Controlled execution.**

The LLM may reason about a task, while Sentinel's execution layer independently determines what the system is actually allowed to do.

---

# 📦 Current Built-in Tools

Current filesystem/system foundation includes:

```text
current_directory
list_files
read_file
create_folder
```

These are intentionally basic.

The important part is not the number of tools.

The important part is that Sentinel now has an SDK capable of automatically discovering and managing future tools.

---

# 🧩 Planned Tool Categories

```text
tools/
├── filesystem/
├── system/
├── network/
├── code/
├── red/
├── soc/
└── purple/
```

Future examples:

### Red

```text
parse_nmap
service_analyzer
recon_summary
web_evidence_parser
```

### SOC

```text
log_reader
ioc_extractor
auth_analyzer
timeline_builder
```

### Purple

```text
technique_mapper
telemetry_mapper
detection_gap_analyzer
```

---

# 🧠 Memory

Sentinel contains foundations for both:

### Short-Term Memory

Conversation context during the current session.

### Persistent Memory

SQLite-backed storage for information that should survive application restarts.

Future versions are planned to include semantic retrieval for:

* Projects
* Security investigations
* Preferences
* Previous findings
* Learning progress
* Environment information

---

# 🏗️ Project Structure

```text
SentinelOS/
│
├── ai/
│   ├── client.py
│   ├── engine.py
│   ├── planner.py
│   ├── dispatcher.py
│   ├── modes.py
│   └── prompts.py
│
├── core/
│   ├── command_center.py
│   ├── banner.py
│   └── logger.py
│
├── models/
│   ├── profiles.py
│   ├── registry.py
│   └── router.py
│
├── tools/
│   ├── base.py
│   ├── manager.py
│   ├── registry.py
│   ├── validator.py
│   ├── security.py
│   └── filesystem/
│
├── memory/
├── database/
├── plugins/
├── config/
├── tests/
├── docs/
├── logs/
├── workspace/
│
├── main.py
├── requirements.txt
└── README.md
```

---

# 💻 Requirements

Recommended development environment:

* Windows 11 / Linux
* Python 3.11+
* Ollama
* Git
* VS Code
* Local LLM capable hardware

A GPU is strongly recommended for local inference.

---

# 🚀 Installation

## 1. Clone Sentinel

```powershell
git clone <YOUR_SENTINEL_REPOSITORY>
cd SentinelOS
```

---

## 2. Create a virtual environment

```powershell
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Then activate again.

---

## 3. Install Python dependencies

```powershell
pip install -r requirements.txt
```

---

## 4. Install Ollama

Install Ollama before running Sentinel. Sentinel checks the local runtime on
every model-backed request and starts `ollama serve` automatically when needed.
Fast tool-only commands do not wake the model runtime, and remote Ollama hosts
are never started automatically.

Verify:

```powershell
ollama list
```

---

## 5. Pull models

General assistant:

```powershell
ollama pull qwen3:4b
```

Additional models can be configured through Sentinel's model registry.

---

## 6. Run Sentinel

```powershell
python main.py
```

---

## 7. Run the browser interface

Start the local-only FastAPI interface:

```powershell
python -m uvicorn api.app:app --host 127.0.0.1 --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

The browser console sends every prompt through the existing
`CommandCenter -> Planner -> Dispatcher` flow. Text chat works in all modern
browsers. Voice input depends on the browser's Speech Recognition support;
spoken responses use the browser's local speech engine when enabled.

The interface reports whether Ollama is online or waiting in auto-start mode.
Long requests show their current phase and elapsed time while the model starts
or generates a response.

Keep the server bound to `127.0.0.1`. The alpha interface is intended for one
local operator and does not provide network authentication.

---

# 🧪 Tests

Sentinel uses `pytest`.

Run the full test suite:

```powershell
python -m pytest -v
```

Tests cover areas such as:

* Tool discovery
* Tool metadata
* Parameter validation
* Tool execution
* Workspace sandboxing
* Planner behavior
* Red / SOC / Purple routing
* Core application flow

---

# 🛡️ Design Principles

## 1. Local First

Sentinel should remain useful without depending on cloud AI providers whenever practical.

## 2. Models Are Replaceable

The application should not depend on one specific LLM.

## 3. Tools Are Discoverable

Adding a capability should not require editing the Sentinel core.

## 4. The Brain Does Not Perform the Work

The Planner decides.

The Dispatcher routes.

The Tool Manager executes.

## 5. Evidence Over Hallucination

Sentinel should never claim a tool succeeded without receiving actual execution results.

## 6. Broad Reasoning, Controlled Execution

Conversational and analytical capabilities are separate from machine permissions.

## 7. Red + Blue = Purple

Sentinel is designed to understand both sides of cybersecurity rather than treating offensive and defensive security as isolated domains.

---

# 🗺️ Roadmap

## Alpha

* [x] Local AI
* [x] AI Client
* [x] Model Registry
* [x] Model Router
* [x] Tool SDK
* [x] Automatic Tool Discovery
* [x] Tool Validation
* [x] Tool Execution
* [x] Workspace Sandbox
* [x] Planner
* [x] Red / SOC / Purple Routing
* [x] Pytest Foundation

## Alpha 0.2

* [ ] Tool Permission Engine
* [ ] Tool Result → AI Reasoning
* [ ] Red Team Tool Pack
* [ ] SOC Tool Pack
* [ ] Purple Team Correlation
* [ ] Improved Persistent Memory
* [ ] Security Investigation Memory

## Beta

* [ ] Nmap integration
* [ ] PCAP analysis
* [ ] Security log ingestion
* [ ] Detection engineering
* [ ] CVE intelligence
* [ ] Report generation
* [ ] Plugin loader
* [x] Local FastAPI interface
* [x] Voice-capable command console
* [ ] Advanced security dashboard

## v1.0

Target:

> **A modular local AI security operating system capable of assisting Red Team, SOC, and Purple Team workflows through specialized models, memory, autonomous planning, and extensible tools.**

---

# 🧩 Plugin Vision

Long term, extending Sentinel should look like:

```text
plugins/
└── my_plugin/
    ├── tools/
    └── plugin.py
```

Drop the plugin into Sentinel.

Restart.

Sentinel discovers the new capability.

No modification to the core should be required.

---

# 🤝 Contributing

Sentinel OS is currently experimental, but the architecture is being designed with open-source extensibility in mind.

General contribution principles:

* Keep modules focused.
* Add tests for new functionality.
* Avoid hardcoded model dependencies.
* Prefer tool discovery over manual registration.
* Keep execution separate from reasoning.
* Do not fabricate tool results.
* Update documentation when architecture changes.

---

# ⚠️ Development Notice

Sentinel OS is currently an experimental research project.

Interfaces, module names, APIs, and architecture may change rapidly during Alpha development.

Do not treat current builds as production security infrastructure.

---

# 🛡️ Sentinel Philosophy

```text
Think deeply.
Verify evidence.
Use the right model.
Choose the right tool.
Understand the attacker.
Understand the defender.
Connect both sides.
```

**Sentinel OS**

*One intelligence. Red, Blue, and Purple.*
