"""
直接调用本地 LLM API（不经过 Aider）
用于 Plan 生成和结果分析
"""

import json
import re
import sys
import time
import requests
from config import (
    ANALYSIS_MAX_TOKENS,
    LLM_BASE_URL,
    LLM_API_KEY,
    LLM_MODEL,
    LLM_TIMEOUT,
    LLM_TOTAL_TIMEOUT,
    PLAN_MAX_TOKENS,
    PLAN_TOTAL_TIMEOUT,
    SCRIPT_MAX_TOKENS,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def chat(
    messages: list[dict],
    temperature: float = 0.2,
    label: str = "",
    max_tokens: int = ANALYSIS_MAX_TOKENS,
    total_timeout: int | None = None,
) -> str:
    """
    流式请求 LLM，实时显示进度点，避免长思考时 TCP 超时。
    自动过滤 <think>...</think> 块，只返回最终答案。
    """
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    if label:
        print(f"  🤔 {label} ", end="", flush=True)
    else:
        print(f"  🤔 Thinking ", end="", flush=True)

    full_text = ""
    token_count = 0
    reasoning_count = 0
    started_at = time.monotonic()
    finish_reason = None
    _total_timeout = total_timeout if total_timeout is not None else LLM_TOTAL_TIMEOUT

    try:
        with requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=LLM_TIMEOUT,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                elapsed = time.monotonic() - started_at
                if elapsed > _total_timeout:
                    raise TimeoutError(
                        f"{label or 'LLM request'} exceeded the "
                        f"{_total_timeout}s total limit"
                    )
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    choice = chunk["choices"][0]
                    finish_reason = choice.get("finish_reason") or finish_reason
                    delta_data = choice["delta"]
                    reasoning = delta_data.get("reasoning_content", "")
                    if reasoning:
                        reasoning_count += 1
                    delta = delta_data.get("content", "")
                    if delta:
                        full_text += delta
                        token_count += 1
                    total_chunks = token_count + reasoning_count
                    if total_chunks and total_chunks % 100 == 0:
                        elapsed = int(time.monotonic() - started_at)
                        print(
                            f"\r  🤖 {label or 'Thinking'}: "
                            f"{token_count} answer + {reasoning_count} reasoning "
                            f"chunks, {elapsed}s",
                            end="",
                            flush=True,
                        )
                except (KeyError, TypeError, json.JSONDecodeError):
                    continue
    except requests.Timeout as exc:
        elapsed = int(time.monotonic() - started_at)
        raise TimeoutError(
            f"{label or 'LLM request'} timed out after {elapsed}s without data"
        ) from exc

    elapsed = int(time.monotonic() - started_at)
    print(
        f"\r  🤖 {label or 'Thinking'}: finished in {elapsed}s "
        f"({token_count} answer + {reasoning_count} reasoning chunks, "
        f"reason={finish_reason or 'done'})",
        flush=True,
    )

    if not full_text.strip():
        raise ValueError(
            f"{label or 'LLM request'} returned no answer content "
            f"(reason={finish_reason or 'unknown'}, "
            f"reasoning_chunks={reasoning_count})"
        )

    # 去掉 <think>...</think> 块，只保留答案
    answer = re.sub(r"<think>.*?</think>", "", full_text, flags=re.DOTALL).strip()
    return answer if answer else full_text


def make_plan(
    task: str,
    project_path: str,
    file_list: list[str],
    file_contents: dict[str, str] | None = None,
) -> list[dict]:
    """
    让 LLM 把任务拆成有序步骤，返回 plan 列表。
    file_contents: {相对路径: 文件内容}，注入小型关键文件供 LLM 直接阅读。
    步骤类型：
      script   — LLM 直接写完整 Python 脚本（数据分析/参数扫描首选）
      code     — 调用 Aider 修改现有文件（仅用于改已有代码）
      command  — 执行 shell 命令
      analysis — 分析前序输出，动态生成后续步骤
    """
    file_summary = "\n".join(file_list[:50])

    contents_block = ""
    if file_contents:
        parts = []
        for path, content in file_contents.items():
            parts.append(f"### {path}\n```python\n{content}\n```")
        contents_block = "\n\nKey file contents:\n\n" + "\n\n".join(parts)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a software engineering planner running in a Linux Docker container. "
                "Break down the user's task into high-level ordered steps. Keep the plan SHORT (under 15 steps). "
                "Step types:\n"
                "  'script'  — write and run a self-contained Python script. "
                "Include 'filename' and a clear 'description' of exactly what the script must do. "
                "Do NOT include 'code' — the script will be generated at execution time.\n"
                "  'code'    — modify existing source files via Aider. Include 'files' array.\n"
                "  'command' — run a shell command. Include 'command' string.\n"
                "  'analysis'— analyze prior outputs and decide next steps.\n"
                "Prefer 'script' for data analysis and parameter sweeps. "
                "Group related sweeps into ONE script step per parameter (not one per symbol). "
                "Use standard Linux/bash commands. "
                "Return ONLY a JSON array of steps, no explanation.\n"
                "script example: {\"step\":1,\"type\":\"script\","
                "\"description\":\"Sweep KEY_LEVEL_OFFSET 0.03-0.12 for BTC/SOL/BNB, save CSV to results/\","
                "\"filename\":\"sweep_key_level_offset.py\"}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"/no_think\n"
                f"Project path: {project_path}\n"
                f"Files:\n{file_summary}"
                f"{contents_block}\n\n"
                f"Task: {task}"
            ),
        },
    ]
    raw = chat(
        messages,
        temperature=0.1,
        label="Generating plan",
        max_tokens=PLAN_MAX_TOKENS,
        total_timeout=PLAN_TOTAL_TIMEOUT,
    )
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"LLM 没有返回有效的 JSON plan:\n{raw}")
    return json.loads(raw[start:end])


def expand_analysis(task: str, step: dict, context: list[dict], remaining: list[dict]) -> list[dict]:
    """
    将 analysis 步骤展开为具体可执行步骤
    把前面所有步骤的输出传入，让 LLM 基于实际内容生成后续步骤
    """
    context_str = "\n\n".join(
        f"Step {c['step']} ({c['description']}):\n"
        f"Command: {c['command']}\n"
        f"Output: {c['stdout']}\n"
        f"Error: {c['stderr']}"
        for c in context
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a software engineering planner running in a Linux Docker container. "
                "Based on the accumulated context from previous steps, generate concrete next steps. "
                "Use standard Linux/bash commands (cat, ls, grep, python, pip, etc). "
                "Return ONLY a JSON array of steps. "
                "Each step: {\"step\": N, \"type\": \"command\"|\"code\", \"description\": \"...\", "
                "\"command\": \"...\", \"files\": []}. "
                "For code steps, list the target plus all existing implementation files "
                "that must be inspected. Do not use placeholders when real project code exists. "
                "Be specific and actionable."
            ),
        },
        {
            "role": "user",
            "content": (
                f"/no_think\n"
                f"Task: {task}\n\n"
                f"Analysis goal: {step.get('description')}\n\n"
                f"Previous steps output:\n{context_str}\n\n"
                f"Remaining planned steps: {json.dumps(remaining, ensure_ascii=False)}\n\n"
                "Generate the concrete steps to execute next."
            ),
        },
    ]
    raw = chat(
        messages,
        temperature=0.1,
        label="Expanding analysis",
        max_tokens=ANALYSIS_MAX_TOKENS,
    )
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        return []
    return json.loads(raw[start:end])


def analyze_result(
    task: str,
    plan: list[dict],
    step: dict,
    output: str,
    error: str,
    return_code: int,
    context: list[dict] = None,
) -> dict:
    """
    分析执行结果，决定下一步行动
    返回：
    {
        "action": "next" | "retry" | "update_plan" | "done" | "fail",
        "reason": "原因",
        "updated_steps": [...]  # action=update_plan 时有效
    }
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are a software engineering agent running in a Linux Docker container. "
                "Analyze the execution result of a step and decide the next action. "
                "Return ONLY JSON with fields: "
                "action (next/retry/update_plan/done/fail), "
                "reason (string), "
                "updated_step (object, the corrected step to retry with, only if action=retry), "
                "updated_steps (array, only if action=update_plan). "
                "Use standard Linux/bash commands (cat, ls, grep, rm, cp, mv, which). "
                "Use 'done' only if the entire task is complete. "
                "Use 'fail' only if the error is unrecoverable. "
                "A return code of 0 means the command completed successfully. "
                "Never retry solely because stdout is truncated or lacks a completion line."
            ),
        },
        {
            "role": "user",
            "content": (
                f"/no_think\n"
                f"Task: {task[:500]}\n\n"  # Truncate task to avoid bloating context
                f"Current step: {json.dumps(step, ensure_ascii=False)}\n\n"
                f"Return code: {return_code}\n\n"
                f"stdout:\n{output[:3000]}\n\n"
                f"stderr:\n{error[:2000]}\n\n"
                f"Remaining plan: {json.dumps(plan, ensure_ascii=False)}"
            ),
        },
    ]
    raw = chat(
        messages,
        temperature=0.1,
        label="Analyzing result",
        max_tokens=ANALYSIS_MAX_TOKENS,
    )
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return {"action": "next", "reason": "无法解析分析结果，继续下一步"}
    return json.loads(raw[start:end])


def generate_script(
    description: str,
    file_contents: dict[str, str],
    context: list[dict] | None = None,
) -> str:
    """
    根据步骤描述和项目文件内容，生成完整可运行的 Python 脚本。
    在 script 步骤执行时调用，避免 plan 阶段生成过长的内联代码。
    """
    contents_block = "\n\n".join(
        f"### {path}\n```python\n{content}\n```"
        for path, content in file_contents.items()
    )
    context_block = ""
    if context:
        recent = context[-3:]  # 只传最近 3 步避免 context 膨胀
        context_block = "\n\nRecent execution context:\n" + "\n\n".join(
            f"Step {c['step']} ({c['description']}):\nstdout: {c['stdout'][:500]}"
            for c in recent
        )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a Python expert running in a Linux Docker container. "
                "Write a SHORT, self-contained Python script that fulfills the given task. "
                "CRITICAL: import and reuse the existing project modules (strategy, backtest, "
                "robustness_a_class_runner) — do NOT reimplement their logic. "
                "Follow the pattern in robustness_a_class_runner.py: "
                "patch strategy.PARAM = value, call the backtest function, restore params. "
                "The script must be under 150 lines. Keep it minimal. "
                "Save output CSV/markdown to the paths mentioned in the task. "
                "Print a summary table at the end. "
                "Return ONLY the Python code, no explanation, no markdown fences."
            ),
        },
        {
            "role": "user",
            "content": (
                f"/no_think\n"
                f"Task: {description}\n\n"
                f"Project files:\n{contents_block}"
                f"{context_block}"
            ),
        },
    ]
    return chat(
        messages,
        temperature=0.1,
        label="Generating script",
        max_tokens=SCRIPT_MAX_TOKENS,
        total_timeout=PLAN_TOTAL_TIMEOUT,
    )
