"""
直接调用本地 LLM API（不经过 Aider）
用于 Plan 生成和结果分析
"""

import json
import re
import sys
import requests
from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT


def chat(messages: list[dict], temperature: float = 0.2, label: str = "") -> str:
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
    }

    if label:
        print(f"  🤔 {label} ", end="", flush=True)
    else:
        print(f"  🤔 Thinking ", end="", flush=True)

    full_text = ""
    token_count = 0
    in_think = False

    with requests.post(
        f"{LLM_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        stream=True,
        timeout=LLM_TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
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
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta:
                    full_text += delta
                    token_count += 1
                    # 每 50 个 token 显示一个进度点
                    if token_count % 50 == 0:
                        # 判断是否在 thinking 模式
                        if "<think>" in full_text and "</think>" not in full_text:
                            print(".", end="", flush=True)
                        else:
                            print("▪", end="", flush=True)
            except Exception:
                continue

    print(f" ({token_count} tokens)", flush=True)

    # 去掉 <think>...</think> 块，只保留答案
    answer = re.sub(r"<think>.*?</think>", "", full_text, flags=re.DOTALL).strip()
    return answer if answer else full_text


def make_plan(task: str, project_path: str, file_list: list[str]) -> list[dict]:
    """
    让 LLM 把任务拆成有序步骤，返回 plan 列表
    每个步骤格式：
    {
        "step": 1,
        "type": "code" | "command" | "analysis",
        "description": "做什么",
        "files": ["相关文件"],   # type=code 时有效
        "command": "shell 命令",  # type=command 时有效
    }
    """
    file_summary = "\n".join(file_list[:50])  # 最多展示 50 个文件
    messages = [
        {
            "role": "system",
            "content": (
                "You are a software engineering planner running on Windows. "
                "Break down the user's task into ordered steps. "
                "Each step must be one of: 'code' (write/modify code via Aider), "
                "'command' (run a shell command), or 'analysis' (analyze results and decide next action). "
                "IMPORTANT: Use Windows commands only. "
                "Use 'type' instead of 'cat', 'dir' instead of 'ls', "
                "'findstr' instead of 'grep', 'del' instead of 'rm', 'where' instead of 'which'. "
                "Use Python for file reading when possible (e.g. python -c \"print(open('file').read())\"). "
                "Return ONLY a JSON array of steps, no explanation. "
                "Example: [{\"step\":1,\"type\":\"command\",\"description\":\"Install deps\","
                "\"command\":\"pip install -r requirements.txt\",\"files\":[]}]"
            ),
        },
        {
            "role": "user",
            "content": (
                f"/no_think\n"
                f"Project path: {project_path}\n"
                f"Files:\n{file_summary}\n\n"
                f"Task: {task}"
            ),
        },
    ]
    raw = chat(messages, temperature=0.1, label="Generating plan")
    # 提取 JSON（模型可能会在前后加文字）
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
                "You are a software engineering planner running on Windows. "
                "Based on the accumulated context from previous steps, generate concrete next steps. "
                "Use Windows commands only (type, dir, findstr, python, pip, etc). "
                "Return ONLY a JSON array of steps. "
                "Each step: {\"step\": N, \"type\": \"command\"|\"code\", \"description\": \"...\", "
                "\"command\": \"...\", \"files\": []}. "
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
    raw = chat(messages, temperature=0.1, label="Expanding analysis")
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        return []
    return json.loads(raw[start:end])


def analyze_result(task: str, plan: list[dict], step: dict, output: str, error: str, context: list[dict] = None) -> dict:
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
                "You are a software engineering agent running on Windows. "
                "Analyze the execution result of a step and decide the next action. "
                "Return ONLY JSON with fields: "
                "action (next/retry/update_plan/done/fail), "
                "reason (string), "
                "updated_step (object, the corrected step to retry with, only if action=retry), "
                "updated_steps (array, only if action=update_plan). "
                "IMPORTANT: This is Windows. Use Windows commands (type, dir, findstr, del, copy, move, where) "
                "instead of Unix commands (cat, ls, grep, rm, cp, mv, which). "
                "Use 'done' only if the entire task is complete. "
                "Use 'fail' only if the error is unrecoverable."
            ),
        },
        {
            "role": "user",
            "content": (
                f"/no_think\n"
                f"Task: {task[:500]}\n\n"  # Truncate task to avoid bloating context
                f"Current step: {json.dumps(step, ensure_ascii=False)}\n\n"
                f"stdout:\n{output[:3000]}\n\n"
                f"stderr:\n{error[:2000]}\n\n"
                f"Remaining plan: {json.dumps(plan, ensure_ascii=False)}"
            ),
        },
    ]
    raw = chat(messages, temperature=0.1, label="Analyzing result")
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return {"action": "next", "reason": "无法解析分析结果，继续下一步"}
    return json.loads(raw[start:end])
