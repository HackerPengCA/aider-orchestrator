"""
执行器：负责执行单个 plan 步骤
- script:   LLM 直接生成完整 Python 脚本，写入文件后执行（首选）
- code:     调用 Aider 修改现有文件（仅用于改已有代码）
- command:  在沙盒内执行 shell 命令
- analysis: 纯分析，不执行
"""

import subprocess
import sys
from pathlib import Path
from sandbox import Sandbox
from config import AIDER_ARGS, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, AIDER_TIMEOUT
from llm_client import generate_script


def run_step(
    step: dict,
    sandbox: Sandbox,
    file_contents: dict[str, str] | None = None,
    context: list[dict] | None = None,
) -> tuple[str, str, int]:
    """
    执行一个步骤，返回 (stdout, stderr, returncode)
    """
    step_type = step.get("type", "command")

    if step_type == "script":
        return _run_script_step(step, sandbox, file_contents=file_contents, context=context)
    elif step_type == "code":
        return _run_code_step(step, sandbox)
    elif step_type == "command":
        return _run_command_step(step, sandbox)
    elif step_type == "analysis":
        return step.get("description", "analysis step"), "", 0
    else:
        return "", f"未知步骤类型: {step_type}", 1


def _run_script_step(
    step: dict,
    sandbox: Sandbox,
    file_contents: dict[str, str] | None = None,
    context: list[dict] | None = None,
) -> tuple[str, str, int]:
    """执行 script 步骤：若无内联 code，先调 LLM 生成脚本再执行"""
    code = step.get("code", "").strip()
    filename = step.get("filename", f"step_{step.get('step', 0)}.py")

    if not code:
        print(f"\n  🤖 生成脚本：{step.get('description', '')}")
        try:
            code = generate_script(
                description=step.get("description", ""),
                file_contents=file_contents or {},
                context=context,
            )
        except Exception as e:
            return "", f"脚本生成失败: {e}", 1
        # strip markdown fences if model wraps in ```python ... ```
        if code.startswith("```"):
            code = "\n".join(
                line for line in code.splitlines()
                if not line.strip().startswith("```")
            )

    scripts_dir = sandbox.project_path / ".orch_scripts"
    scripts_dir.mkdir(exist_ok=True)
    script_path = scripts_dir / filename
    sandbox.safe_write(str(script_path), code)
    print(f"\n  📝 脚本已写入: {script_path}")

    try:
        return sandbox.run_command(f"PYTHONPATH={sandbox.project_path} python3 {script_path}")
    except PermissionError as e:
        return "", str(e), 1
    except subprocess.TimeoutExpired:
        return "", "脚本执行超时", 1


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
