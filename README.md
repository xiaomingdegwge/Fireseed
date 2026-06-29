# Fireseed

Fireseed is a minimal, runnable clone of the core loop used in `cc-mini`.
It was split out from `cc-mini/docs/CC_DUP` into its own repository while
preserving the original learning-oriented commit history.

- REPL input loop
- Engine turn loop (`assistant -> tool_use -> tool_result -> assistant`)
- Tool abstraction (`Read`, `Edit`, `Write`, `Glob`, `Grep`, `Bash`)
- Permission checks (read-only tools auto-allow; `Edit`, `Write`, and `Bash` ask)
- Session persistence (JSONL)
- Real provider support (`anthropic` / `openai`) + mock fallback
- API key fallback loading from environment and `~/.bashrc`
- TOML config files (`~/.config/fireseed/config.toml`, `.fireseed.toml`, or `--config`)
- Model aliases (`sonnet`, `opus`, `haiku`, `best`) and model-aware default max tokens
- Optional Bash sandbox via bubblewrap (`[sandbox]` TOML config)
- API retry and retryable error handling
- Read-only tool parallel execution batches
- Session resume support (`--resume`)
- `load_dotenv()` (`.env` in cwd) + `~/.bashrc` key fallbacks
- Rich status spinner + **Esc to cancel** (TTY) when not using `--plain`
- `build_system_prompt` with working directory
- `/help`, `/clear`, `/sessions`, `/history`, `/resume`, `/compact`, and `/cost` slash commands
- Skills: `/skills`, `/review`, `/commit`, `/test`, `/simplify`, plus `.fireseed/skills/*/SKILL.md`
- `Glob` tool (read-only, can run in parallel with other read-only tools)

## Quick Start

Install locally for development:

```bash
python3 -m pip install -e ".[dev]"
```

```bash
python3 app.py --provider anthropic
```

After installing, you can also run:

```bash
fireseed --provider anthropic
```

Run single prompt:

```bash
python3 app.py --provider anthropic --print "hello"
```

Resume from a previous session:

```bash
python3 app.py --provider anthropic --resume 1
```

or by prefix:

```bash
python3 app.py --provider anthropic --resume 20260413
```

Enable all write/bash approvals:

```bash
python3 app.py --provider anthropic --auto-approve
```

Mock mode (no network):

```bash
python3 app.py --provider mock
```

Interactive REPL without Rich spinner (plain text only):

```bash
python3 app.py --provider anthropic --plain
```

View a saved JSONL session as a readable timeline:

```bash
python3 session_viewer.py .cc_dup_sessions/20260629-173248.jsonl
```

Export the same session to a collapsible browser view:

```bash
python3 session_viewer.py .cc_dup_sessions/20260629-173248.jsonl --html
```

After installing the package, the same viewer is available as:

```bash
fireseed-session-viewer .cc_dup_sessions/20260629-173248.jsonl --html
```

Create a `.env` in the project root or cwd (same convention as cc-mini):

```bash
ANTHROPIC_API_KEY=...
# or ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL for compatible endpoints
```

Note: the first migrated version still accepts the `CC_DUP_*` environment
variable names for compatibility with the teaching code it was split from.

## TOML Config

Fireseed loads config in this order:

1. `~/.config/fireseed/config.toml`
2. `.fireseed.toml` in the current working directory
3. explicit `--config <path>`

CLI flags override environment variables, and environment variables override TOML.

```toml
provider = "anthropic"
model = "sonnet"

[anthropic]
api_key = "sk-ant-..."
base_url = "https://your-gateway.example.com"
```

OpenAI-compatible example:

```toml
provider = "openai"

[openai]
api_key = "sk-..."
base_url = "https://your-openai-gateway.example.com/v1"
model = "gpt-4.1-mini"
max_tokens = 8192
effort = "medium"
```

Sandbox example:

```toml
[sandbox]
enabled = true
auto_allow_bash = true
excluded_commands = ["docker *"]
unshare_net = true

[sandbox.filesystem]
allow_write = ["."]
deny_write = [".fireseed.toml"]
deny_read = [".env"]
```

When sandbox is enabled and `bwrap` is available, Bash commands are wrapped
before execution. With `auto_allow_bash = true`, sandboxed Bash commands skip
the normal permission prompt; excluded commands still use the regular Bash path.

## API Key Resolution Order

For `--provider anthropic`, key names are checked in order:

1. `FIRESEED_API_KEY`
2. `CC_DUP_API_KEY`
3. `ANTHROPIC_API_KEY`
4. `ANTHROPIC_AUTH_TOKEN`
5. exported values parsed from `~/.bashrc` with same names

For `--provider openai`, key names:

1. `FIRESEED_API_KEY`
2. `CC_DUP_API_KEY`
3. `OPENAI_API_KEY`
4. exported values parsed from `~/.bashrc` with same names

If you see:

`No API key found for provider=openai`

set one of:

- `OPENAI_API_KEY`
- `FIRESEED_API_KEY`
- `CC_DUP_API_KEY`

in your shell environment or `~/.bashrc`.

`base_url` resolution order:

1. `--base-url`
2. `FIRESEED_BASE_URL`
3. `CC_DUP_BASE_URL`
4. provider-specific env (`ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL`)
5. exported values parsed from `~/.bashrc`

## Built-in Tool Triggers (Mock LLM)

In `--provider mock`, the model uses simple prefixes in user input:

- `/tool read <path>`
- `/tool grep <pattern> :: <path>`
- `/tool edit <path> :: <old> :: <new>`
- `/tool write <path> :: <content>`
- `/tool bash <command>`
- `/tool ask <question>`
- `/tool plan`
- `/tool exit-plan`

Example:

```text
/tool read README.md
```

The engine will emit tool events, execute the tool, feed `tool_result` back to the model, and then output the final assistant response.

`/tool ask` is useful for checking the AskUserQuestion flow: Fireseed shows a terminal choice menu, waits for the user answer, writes that answer back as `tool_result`, then continues the same turn.

`/tool plan` and `/tool exit-plan` check the Plan Mode flow in mock mode. Real models can call `EnterPlanMode` before larger edits, write the plan file, then call `ExitPlanMode`.

## Additional REPL Commands

- `/help` : list available commands
- `/skills` : list available built-in/project/user skills
- `/review [focus]` : review changed code without editing
- `/commit [message]` : stage relevant changes and create a commit
- `/test [filter]` : run and analyze tests
- `/simplify [focus]` : improve changed code for clarity and reuse
- `/sandbox` : show sandbox status
- `/sandbox deps` : show bubblewrap dependency check
- `/sandbox mode <auto-allow|regular|disabled>` : change sandbox mode and save `.fireseed.toml`
- `/sandbox exclude <pattern>` : add a command exclusion pattern and save `.fireseed.toml`
- `/sessions` : list local saved sessions
- `/history` : alias for `/sessions`
- `/resume <number|prefix>` : resume a saved session inside the REPL
- `/compact [extra instructions]` : summarize older context and keep recent messages
- `/cost` : show token usage and estimated cost
- `/clear` : reset in-memory messages

Project skills can be added as:

```text
.fireseed/skills/my-skill/SKILL.md
```

with optional frontmatter:

```markdown
---
name: my-skill
description: Explain what this skill does
arguments: focus
---
Use this reusable prompt with $ARGUMENTS.
```
