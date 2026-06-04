"""
Orchestrator 配置

架构说明：
  执行环境：Windows（Orchestrator / Aider / Shell 命令全在 Windows 上跑）
  LLM：     MacOS 远程（llama.cpp + Qwen3），通过 SSH 隧道访问
  端点：    http://localhost:8081/v1
"""

LLM_BASE_URL = "http://localhost:8081/v1"
LLM_API_KEY = "none"
LLM_MODEL = "openai/qwen3.6-27b"
LLM_TIMEOUT = 600  # 流式模式下为单次 chunk 超时，LLM 思考时间不受此限制

# Aider 调用超时（写代码比分析耗时更长）
AIDER_TIMEOUT = 7200  # 2 小时，Qwen3 长上下文生成可能很慢

# Aider 启动参数
AIDER_ARGS = [
    "--no-stream",
    "--timeout", "7200",   # 单次 LLM 请求超时，与 AIDER_TIMEOUT 一致
    "--map-tokens", "0",   # 关掉 repo map，减少输入 token，加快速度
    "--max-chat-history-tokens", "200000",
    "--edit-format", "diff",
    "--yes",               # 自动确认，不交互
]

# 安全：最大重试次数
MAX_RETRIES = 5

# 安全：单次命令最大执行时间（秒）
COMMAND_TIMEOUT = 120
