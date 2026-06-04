# Aider Orchestrator

A lightweight autonomous coding agent that wraps [Aider](https://github.com/Aider-AI/aider) with a **Plan → Execute → Analyze → Loop** cycle, powered by a local LLM via llama.cpp.

## What it does

Instead of manually running Aider for each change, the Orchestrator:

1. Takes a high-level task description
2. Uses the LLM to generate an ordered execution plan
3. Executes each step — either running shell commands or calling Aider to write/modify code
4. Feeds results back to the LLM to decide: next step / retry / update plan / done
5. Loops until the task is complete or fails

## Architecture

```
User Input
    │
    ▼
Orchestrator (main.py)
    ├── LLM Client (llm_client.py)   — Plan generation & result analysis
    ├── Sandbox (sandbox.py)         — Security: restrict writes/exec to project dir
    └── Executor (executor.py)
            ├── Shell commands       — Run tests, install deps, start servers
            └── Aider               — Write & modify code
```

## Security Model

- **Write / Execute**: restricted to the specified project directory
- **Path traversal protection**: `../` escapes are blocked
- **Read**: unrestricted
- **Max retries**: 5 (configurable)
- **Command timeout**: 120s (configurable)

## Requirements

- Python 3.11+
- [Aider](https://aider.chat) (`pip install aider-chat`)
- A local LLM served via OpenAI-compatible API (llama.cpp, Ollama, etc.)

## Setup

```bash
git clone https://github.com/<your-username>/aider-orchestrator
cd aider-orchestrator
pip install aider-chat requests
```

Edit `config.py` to point to your LLM endpoint:

```python
LLM_BASE_URL = "http://localhost:8081/v1"
LLM_MODEL    = "openai/your-model-name"
```

## Usage

```bash
python main.py --project /path/to/your/project
```

Then type a task at the prompt:

```
📝 输入任务: Write a Flask hello world app, run it, and verify it returns 200
```

The agent will plan, execute, debug, and iterate automatically.

## Tested With

- **Model**: Qwen3 27B / 35B (via llama.cpp)
- **OS**: Windows 11
- **LLM server**: llama.cpp with OpenAI-compatible API

## License

MIT
