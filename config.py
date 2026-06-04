"""
Orchestrator Configuration

Architecture:
  Execution env : Windows (Orchestrator / Aider / shell commands all run on Windows)
  LLM           : macOS remote (llama.cpp + Qwen3), accessed via SSH tunnel
  Endpoint      : http://localhost:8081/v1
"""

LLM_BASE_URL = "http://localhost:8081/v1"
LLM_API_KEY  = "none"
LLM_MODEL    = "openai/qwen3.6-27b"

# Streaming mode: this is per-chunk idle timeout, NOT total response time.
# As long as tokens keep flowing the connection stays alive.
LLM_TIMEOUT  = 600

# Aider subprocess timeout (code generation can be very slow on local LLM)
AIDER_TIMEOUT = 7200  # 2 hours

# Aider CLI flags passed every invocation
AIDER_ARGS = [
    "--no-stream",
    "--timeout", "7200",    # Aider's own LLM request timeout
    "--map-tokens", "0",    # Disable repo map — files are passed explicitly
    "--max-chat-history-tokens", "200000",
    # edit-format omitted: let Aider auto-select (whole for new files, diff for edits)
    "--yes",                # Non-interactive: auto-confirm all changes
]

# Safety limits
MAX_RETRIES     = 5    # Max retries per step before giving up
COMMAND_TIMEOUT = 300  # Max seconds for a single shell command (increased for long backtests)
