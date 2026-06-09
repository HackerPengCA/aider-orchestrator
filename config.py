"""
Orchestrator Configuration

Architecture:
  Execution env : Docker container (Linux)
  LLM           : host machine (llama.cpp + Qwen3), accessed via host.docker.internal
  Endpoint      : http://host.docker.internal:8081/v1
"""

LLM_BASE_URL = "http://host.docker.internal:8081/v1"
LLM_API_KEY  = "none"
LLM_MODEL    = "openai/qwen3.6-27b"
AIDER_MODEL_SETTINGS_FILE = "/app/.aider.model.settings.yml"

# Streaming mode: this is per-chunk idle timeout, NOT total response time.
# As long as tokens keep flowing the connection stays alive.
LLM_TIMEOUT  = 600
LLM_TOTAL_TIMEOUT = 180       # analysis/expand calls
PLAN_TOTAL_TIMEOUT = 600      # plan generation with inline scripts can be long
PLAN_MAX_TOKENS = 1024   # plan is high-level only; scripts are generated at execution time
SCRIPT_MAX_TOKENS = 4096  # per-script code generation
ANALYSIS_MAX_TOKENS = 1024

# Aider subprocess timeout (code generation can be very slow on local LLM)
AIDER_TIMEOUT = 900

# Aider CLI flags passed every invocation
AIDER_ARGS = [
    "--stream",
    "--no-pretty",
    "--no-show-model-warnings",
    "--no-auto-commits",
    "--model-settings-file", AIDER_MODEL_SETTINGS_FILE,
    "--timeout", "600",
    "--map-tokens", "0",    # Disable repo map — files are passed explicitly
    "--max-chat-history-tokens", "200000",
    # edit-format omitted: let Aider auto-select (whole for new files, diff for edits)
    "--yes",                # Non-interactive: auto-confirm all changes
]

# Safety limits
MAX_RETRIES     = 2    # Avoid expensive retry loops caused by ambiguous output
COMMAND_TIMEOUT = 900  # Max seconds for a single shell command (param sweep ~130 runs needs headroom)
