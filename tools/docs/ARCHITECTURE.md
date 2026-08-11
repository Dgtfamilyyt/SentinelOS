# Sentinel OS architecture

## Scope and status

This document describes the code that exists in the repository today. Sentinel
OS is a local, command-line prototype. It has no HTTP API, dashboard, plugin
loader, browser, terminal, voice, or cybersecurity-tool implementation.

The intended orchestration pipeline is:

```text
CommandCenter -> Planner -> Dispatcher -> ToolManager -> Tool
```

`Planner` and `Dispatcher` classes exist, but that pipeline is **not wired into
the runtime**. It must not be treated as the current execution path.

## Active runtime path

`main.py` starts an interactive loop and creates one `CommandCenter`:

```text
stdin
  -> main.main()
  -> CommandCenter.process(prompt)
       -> IntentEngine.classify(prompt)
          -> ToolManager.execute(...)       (recognised filesystem phrases)
          -> AIEngine.ask(prompt)           (all other phrases)
  -> stdout
```

The built-in `/clear` command clears the in-memory `Conversation` held by the
`AIEngine`; `exit` and `quit` end the process. Logging is configured by
`core.logger` and is written to `logs/sentinel.log` relative to the current
working directory.

### Tool requests

`IntentEngine` uses simple string matching for these phrases:

- `list files` -> `list_files`
- `current directory` -> `current_directory`
- `read <filename>` -> `read_file`
- `create folder <name>` -> `create_folder`

`ToolManager` can discover `Tool` subclasses beneath the `tools` package,
validate their metadata and required parameters, register them, and call their
`execute` method. However, `CommandCenter` does not call
`ToolManager.discover()`. Consequently its registry is empty in the normal CLI
startup path and recognised tool requests currently return “Tool not found”.

The argument shapes are also inconsistent: `IntentEngine` emits positional
lists, while `ToolManager.execute()` expects an optional parameters dictionary.
This affects tool calls that need arguments. These are implementation gaps, not
documented capabilities.

### Chat requests and model routing

For non-tool requests, `AIEngine` adds the prompt to `Conversation` and calls
`AIClient`, which sends the full conversation to the local Ollama `chat` API.

There are two model-routing implementations:

- `ai.router.AIRouter.get_model()` selects `GENERAL_MODEL` or `CODER_MODEL`
  from `config.settings` using coding-related keywords.
- `models.router.ModelRouter.choose()` selects a model profile from
  `models.profiles` using an explicit task label.

`AIEngine` currently instantiates `ModelRouter` but calls its nonexistent
`get_model()` method. Therefore the chat path raises `AttributeError` before
an Ollama request is made. `AIRouter` is imported but not used. Model routing
is present in source but is not functioning in the active runtime.

### Planner and dispatcher (present, not active)

`ai.planner.Planner` asks Ollama to return JSON describing either a tool call or
chat response. `core.dispatcher.Dispatcher` accepts a plan with an `action`,
`tool`, and `args`. Neither is constructed or invoked by `CommandCenter`.
There is also an additional `Planner` class at the end of `ai.prompts`, which
duplicates planning responsibility and refers to a nonexistent
`ToolManager.available_tools()` API. It is not imported by the runtime.

Before the intended pipeline can be documented as active, the application needs
one canonical plan schema, tool discovery during startup, compatible manager and
dispatcher call signatures, and integration tests that exercise the full path.

## Memory and storage

`memory.conversation.Conversation` stores the current chat history in process
memory only. Calling `/clear` restores it to a single system prompt; exiting the
process discards it.

`memory.persistent.PersistentMemory` stores string key/value pairs in SQLite at
`database/memory.db`. The `memories` table is created only by manually running
`database/init_db.py`. `MemoryManager` wraps this store, but neither it nor
`PersistentMemory` is connected to `CommandCenter` or `AIEngine`; prompts
and responses are not persistently remembered by the CLI.

## Security boundaries

The trust boundary is between user/model-selected tool arguments and host
filesystem operations. The current filesystem tools (`list_files`, `read_file`,
and `create_folder`) pass supplied paths directly to Python `os` or `open`
calls. There is no configured workspace root, path traversal prevention,
allowlist, confirmation policy, authorization layer, sandbox, or audit record
for tool actions.

`ToolValidator` only validates tool metadata and presence of parameters. It is
not a permissions system. The current implementation should therefore be run
only in a trusted local development environment, not exposed to untrusted users
or a model with unconstrained filesystem inputs.

## Repository layout

```text
ai/          Ollama client, prompts, intent matching, planning, routing
core/        CLI coordination, dispatcher, logging, banner, version
tools/       Tool base class, discovery/validation/registry, filesystem tools
models/      Static model profiles and role-based router
memory/      In-memory conversation and standalone SQLite key/value memory
database/    SQLite connection helper and schema-initialization script
config/      Model-name settings
tests/       Standalone diagnostic scripts (not assertion-based test suite)
api/         Package placeholder only
dashboard/   Package placeholder only
plugins/     Package placeholder only
web/         Package placeholder only
```

## Verification status

The repository does not currently provide a pytest dependency or an
assertion-based automated test suite. Files under `tests/` are executable
diagnostic scripts, and some refer to methods that `ToolManager` does not
implement. The runtime integration issues above should be resolved before this
document is changed to describe the intended Planner-to-Dispatcher pipeline as
operational.
