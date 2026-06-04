# Aider Orchestrator

A lightweight autonomous coding agent that wraps [Aider](https://github.com/Aider-AI/aider) with a **Plan → Execute → Analyze → Loop** cycle, powered by a local LLM via llama.cpp.

## What it does

Instead of manually running Aider for each change, the Orchestrator:

1. Takes a high-level task description (text or file path)
2. Uses the LLM to generate an ordered execution plan
3. Executes each step — shell commands or Aider code generation
4. Feeds results back to the LLM to decide: next / retry / update plan / done
5. Loops until the task is complete

## Architecture

```
Windows machine
  │
  ├── Orchestrator (main.py)
  │     ├── LLM Client (llm_client.py)   — streaming, plan & analysis
  │     ├── Sandbox (sandbox.py)         — security restrictions
  │     └── Executor (executor.py)
  │           ├── Shell commands         — run tests, scripts, installs
  │           └── Aider                  — write & modify code
  │
  └── SSH tunnel → macOS (llama.cpp + Qwen3)
```

## Security Model

- **Write / Execute**: restricted to the specified project directory
- **Path traversal**: `../` escapes are blocked
- **Read**: unrestricted
- **Max retries per step**: 5
- **Command timeout**: 300s (configurable in `config.py`)

## Requirements

- Python 3.11+
- [Aider](https://aider.chat): `pip install aider-chat`
- Local LLM via OpenAI-compatible API (llama.cpp, Ollama, etc.)

## Setup

```bash
git clone https://github.com/HackerPengCA/aider-orchestrator
cd aider-orchestrator
pip install aider-chat requests
```

Edit `config.py` to match your LLM endpoint:

```python
LLM_BASE_URL = "http://localhost:8081/v1"
LLM_MODEL    = "openai/your-model-name"
```

## Usage

```bash
python main.py --project /path/to/your/project
```

At the prompt, enter a task as text or a file path:

```
# Plain text
📝 Enter task: Write a Flask hello world app and run it

# File path — content is auto-loaded into the prompt
📝 Enter task: C:\Projects\myplan.md

# Mixed
📝 Enter task: Follow this plan: C:\Projects\myplan.md
```

## Key Design Decisions

**Streaming LLM calls** — Qwen3 runs in thinking mode and can take 10–60 minutes per response. Streaming keeps the connection alive regardless of how long the model thinks.

**No repo map** — `--map-tokens 0` disables Aider's project scan. Files are passed explicitly per step, keeping the prompt short and generation fast.

**Auto edit format** — Aider selects `whole` for new files and `diff` for existing ones. Forcing `diff` on a new file produces 0-byte output.

**Windows-aware commands** — The executor auto-translates Unix commands (`cat`→`type`, `ls`→`dir`, etc.) as a fallback. The LLM system prompt also instructs it to use Windows commands directly.

**Context passing** — Each step's output is accumulated and passed to subsequent analysis steps, so the LLM always has full context when making decisions.

## Tested With

- **Model**: Qwen3 27B / 35B via llama.cpp
- **OS**: Windows 11
- **LLM server**: llama.cpp with OpenAI-compatible API

## License

MIT
