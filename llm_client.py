"""
直接调用本地 LLM API（不经过 Aider）
用于 Plan 生成和结果分析
"""

import json
import requests
from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT


def chat(messages: list[dict], temperature: float = 0.2) -> str:
    """发送对话请求，返回模型回复文本"""
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    resp = requests.post(
        f"{LLM_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


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
                "You are a software engineering planner. "
                "Break down the user's task into ordered steps. "
                "Each step must be one of: 'code' (write/modify code via Aider), "
                "'command' (run a shell command), or 'analysis' (analyze results and decide next action). "
                "Return ONLY a JSON array of steps, no explanation. "
                "Example: [{\"step\":1,\"type\":\"command\",\"description\":\"Install deps\","
                "\"command\":\"pip install -r requirements.txt\",\"files\":[]}]"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Project path: {project_path}\n"
                f"Files:\n{file_summary}\n\n"
                f"Task: {task}"
            ),
        },
    ]
    raw = chat(messages, temperature=0.1)
    # 提取 JSON（模型可能会在前后加文字）
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"LLM 没有返回有效的 JSON plan:\n{raw}")
    return json.loads(raw[start:end])


def analyze_result(task: str, plan: list[dict], step: dict, output: str, error: str) -> dict:
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
                "You are a software engineering agent. "
                "Analyze the execution result of a step and decide the next action. "
                "Return ONLY JSON with fields: action (next/retry/update_plan/done/fail), "
                "reason (string), updated_steps (array, only if action=update_plan). "
                "Use 'done' only if the entire task is complete. "
                "Use 'fail' only if the error is unrecoverable."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Task: {task}\n\n"
                f"Current step: {json.dumps(step, ensure_ascii=False)}\n\n"
                f"stdout:\n{output[:3000]}\n\n"
                f"stderr:\n{error[:2000]}\n\n"
                f"Remaining plan: {json.dumps(plan, ensure_ascii=False)}"
            ),
        },
    ]
    raw = chat(messages, temperature=0.1)
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return {"action": "next", "reason": "无法解析分析结果，继续下一步"}
    return json.loads(raw[start:end])
