"""
Orchestrator 配置
"""

LLM_BASE_URL = "http://localhost:8081/v1"
LLM_API_KEY = "none"
LLM_MODEL = "openai/qwen3.6-27b"
LLM_TIMEOUT = 300

# Aider 启动参数
AIDER_ARGS = [
    "--no-stream",
    "--timeout", "300",
    "--map-tokens", "8192",
    "--max-chat-history-tokens", "200000",
    "--edit-format", "diff",
    "--yes",  # 自动确认，不交互
]

# 安全：最大重试次数
MAX_RETRIES = 5

# 安全：单次命令最大执行时间（秒）
COMMAND_TIMEOUT = 120
