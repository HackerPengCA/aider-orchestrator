"""
执行器：负责执行单个 plan 步骤
- code: 调用 Aider 修改代码
- command: 在沙盒内执行 shell 命令
- analysis: 纯分析，不执行
"""

import subprocess
import sys
from pathlib import Path
from sandbox import Sandbox
from config import AIDER_ARGS, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL


def run_step(step: dict, sandbox: Sandbox) -> tuple[str, str, int]:
    """
    执行一个步骤，返回 (stdout, stderr, returncode)
    """
    step_type = step.get("type", "command")

    if step_type == "code":
        return _run_code_step(step, sandbox)
    elif step_type == "command":
        return _run_command_step(step, sandbox)
    elif step_type == "analysis":
        return step.get("description", "analysis step"), "", 0
    else:
        return "", f"未知步骤类型: {step_type}", 1


def _run_command_step(step: dict, sandbox: Sandbox) -> tuple[str, str, int]:
    command = step.get("command", "")
    if not command:
        return "", "步骤缺少 command 字段", 1
    try:
        stdout, stderr, rc = sandbox.run_command(command)
        return stdout, stderr, rc
    except PermissionError as e:
        return "", str(e), 1
    except subprocess.TimeoutExpired:
        return "", "命令执行超时", 1


def _run_code_step(step: dict, sandbox: Sandbox) -> tuple[str, str, int]:
    """调用 Aider 修改代码"""
    description = step.get("description", "")
    files = step.get("files", [])

    # 把相对路径转为绝对路径
    abs_files = []
    for f in files:
        p = Path(f)
        if not p.is_absolute():
            p = sandbox.project_path / f
        abs_files.append(str(p))

    cmd = [
        sys.executable, "-m", "aider",
        "--model", LLM_MODEL,
        "--openai-api-base", LLM_BASE_URL,
        "--openai-api-key", LLM_API_KEY,
        *AIDER_ARGS,
        "--message", description,
        *abs_files,
    ]

    print(f"\n  🤖 调用 Aider: {description}")
    print(f"  📄 文件: {abs_files}")

    result = subprocess.run(
        cmd,
        cwd=str(sandbox.project_path),
        capture_output=True,
        text=True,
        timeout=600,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout, result.stderr, result.returncode
