"""
执行器：负责执行单个 plan 步骤
- code: 调用 Aider 修改代码
- command: 在沙盒内执行 shell 命令
- analysis: 纯分析，不执行
"""

import subprocess
import sys
import platform
from pathlib import Path
from sandbox import Sandbox
from config import AIDER_ARGS, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, AIDER_TIMEOUT

IS_WINDOWS = platform.system() == "Windows"

# Unix->Windows command mapping
WIN_CMD_MAP = {
    "cat ":   "type ",
    "ls ":    "dir ",
    "ls\n":   "dir\n",
    "ls":     "dir",
    "grep ":  "findstr ",
    "rm ":    "del ",
    "cp ":    "copy ",
    "mv ":    "move ",
    "mkdir ": "mkdir ",
    "touch ": "type nul > ",
    "which ": "where ",
    "pwd":    "cd",
    "echo ":  "echo ",
}


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


def _normalize_command(command: str) -> str:
    """在 Windows 上自动替换 Unix 命令"""
    if not IS_WINDOWS:
        return command
    for unix_cmd, win_cmd in WIN_CMD_MAP.items():
        if command.strip().startswith(unix_cmd.strip()):
            command = win_cmd + command[len(unix_cmd):]
            break
    # 路径分隔符：把 / 换成 \ （仅对路径部分）
    return command


def _run_command_step(step: dict, sandbox: Sandbox) -> tuple[str, str, int]:
    command = step.get("command", "")
    if not command:
        return "", "步骤缺少 command 字段", 1
    command = _normalize_command(command)
    step["command"] = command  # 更新 step，让 retry 用新命令
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
    print("  Aider 正在流式生成；较大的新文件可能需要几分钟。")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(sandbox.project_path),
            capture_output=False,
            timeout=AIDER_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        empty_files = [
            path for path in abs_files
            if Path(path).exists() and Path(path).stat().st_size == 0
        ]
        detail = f"；仍为空的文件: {empty_files}" if empty_files else ""
        return "", f"Aider 在 {AIDER_TIMEOUT} 秒后超时{detail}", 1

    if result.returncode != 0:
        empty_files = [
            path for path in abs_files
            if Path(path).exists() and Path(path).stat().st_size == 0
        ]
        detail = f"；仍为空的文件: {empty_files}" if empty_files else ""
        return "", f"Aider 退出码 {result.returncode}{detail}", result.returncode
    return "", "", result.returncode
