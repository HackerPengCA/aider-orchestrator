"""
Aider Orchestrator — 主入口
用法：python main.py --project <项目路径>
"""

import argparse
import json
import sys
from pathlib import Path

from sandbox import Sandbox
from llm_client import make_plan, analyze_result, expand_analysis
from executor import run_step
from config import MAX_RETRIES


BANNER = """
╔══════════════════════════════════════════╗
║       Aider Orchestrator v0.1            ║
║  自动 Plan → 执行 → Debug → 循环         ║
╚══════════════════════════════════════════╝
"""


def print_plan(plan: list[dict]):
    print("\n📋 执行计划：")
    for step in plan:
        icon = {"code": "🤖", "command": "▶", "analysis": "🔍"}.get(step.get("type"), "•")
        print(f"  {icon} 步骤 {step['step']}: [{step['type']}] {step['description']}")
    print()


def run_task(task: str, sandbox: Sandbox):
    print(f"\n🎯 任务：{task}")
    print(f"📁 项目：{sandbox.project_path}\n")

    # 1. 列出项目文件
    files = sandbox.list_files()
    print(f"📂 发现 {len(files)} 个文件")

    # 2. 生成 Plan
    print("\n⏳ 正在生成执行计划...")
    try:
        plan = make_plan(task, str(sandbox.project_path), files)
    except Exception as e:
        print(f"❌ Plan 生成失败: {e}")
        return
    print_plan(plan)

    # 确认执行
    confirm = input("确认执行？[Y/n] ").strip().lower()
    if confirm == "n":
        print("已取消。")
        return

    # 3. 逐步执行，维护累积上下文
    step_index = 0
    retries = 0
    # 每步输出存入 context，供后续步骤和分析使用
    context: list[dict] = []

    while step_index < len(plan):
        step = plan[step_index]
        print(f"\n{'='*60}")
        print(f"▶ 步骤 {step['step']}/{len(plan)}: {step['description']}")
        print(f"{'='*60}")

        # analysis 步骤：把累积上下文传给 LLM，让它生成具体后续步骤
        if step.get("type") == "analysis":
            try:
                new_steps = expand_analysis(task, step, context, plan[step_index+1:])
            except Exception as e:
                print(f"⚠️  Analysis 展开失败: {e}，跳过")
                step_index += 1
                retries = 0
                continue
            if new_steps:
                plan = plan[:step_index] + new_steps + plan[step_index+1:]
                print(f"  📝 Analysis 展开为 {len(new_steps)} 个具体步骤")
            else:
                step_index += 1
            retries = 0
            continue

        try:
            stdout, stderr, rc = run_step(step, sandbox)
        except Exception as e:
            stderr = str(e)
            stdout = ""
            rc = 1

        # 记录本步骤输出到 context
        context.append({
            "step": step.get("step"),
            "description": step.get("description"),
            "command": step.get("command", ""),
            "stdout": stdout[:3000],
            "stderr": stderr[:1000],
            "rc": rc,
        })

        # 4. 分析结果
        remaining = plan[step_index + 1:]
        try:
            decision = analyze_result(task, remaining, step, stdout, stderr, context)
        except Exception as e:
            print(f"⚠️  结果分析失败: {e}，继续下一步")
            decision = {"action": "next", "reason": "分析失败，跳过"}

        action = decision.get("action", "next")
        reason = decision.get("reason", "")
        print(f"\n  💡 决策: {action} — {reason}")

        if action == "done":
            print("\n✅ 任务完成！")
            break
        elif action == "fail":
            print(f"\n❌ 任务失败: {reason}")
            break
        elif action == "retry":
            retries += 1
            if retries >= MAX_RETRIES:
                print(f"\n❌ 已重试 {MAX_RETRIES} 次，放弃。")
                break
            updated_step = decision.get("updated_step")
            if updated_step:
                plan[step_index] = updated_step
                print(f"  📝 步骤已更新: {updated_step.get('command') or updated_step.get('description')}")
            print(f"  🔄 重试 ({retries}/{MAX_RETRIES})...")
        elif action == "update_plan":
            updated = decision.get("updated_steps", [])
            if updated:
                plan = plan[:step_index + 1] + updated
                print(f"  📝 Plan 已更新，新增 {len(updated)} 个步骤")
            step_index += 1
            retries = 0
        else:  # next
            step_index += 1
            retries = 0

    print(f"\n{'='*60}")
    print("Orchestrator 执行结束")
    print(f"{'='*60}\n")


def main():
    print(BANNER)

    parser = argparse.ArgumentParser(description="Aider Orchestrator")
    parser.add_argument("--project", "-p", help="项目目录路径")
    args = parser.parse_args()

    # 确定项目目录
    if args.project:
        project_path = args.project
    else:
        project_path = input("请输入项目目录路径: ").strip().strip('"')

    try:
        sandbox = Sandbox(project_path)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    print(f"✅ 沙盒已初始化：{sandbox.project_path}")
    print("   安全策略：写入/执行 → 仅限项目目录 | 读取 → 不受限制")

    # 主循环
    while True:
        print()
        task = input("📝 输入任务或文件路径（exit 退出）: ").strip().strip('"')
        if task.lower() in ("exit", "quit", "q"):
            print("再见！")
            break
        if not task:
            continue
        task = resolve_task(task)
        run_task(task, sandbox)


def resolve_task(task: str) -> str:
    """
    如果输入包含文件路径，读取文件内容注入到任务中。
    支持纯路径、说明文字+路径、冒号分隔等各种写法。
    """
    import re
    # 匹配 Windows 绝对路径（含中文目录）
    path_pattern = re.compile(r'[A-Za-z]:[\\\/][^\s,，。；;]+')
    matches = path_pattern.findall(task)

    loaded = []
    remaining_task = task
    for match in matches:
        # 去掉末尾可能粘连的标点
        match = match.rstrip('，。；:：,.')
        p = Path(match)
        if p.exists() and p.is_file():
            content = p.read_text(encoding="utf-8", errors="replace")
            loaded.append(f"[文件：{p.name}]\n{content}")
            remaining_task = remaining_task.replace(match, "").strip().strip(':：').strip()
            print(f"  📄 已加载文件：{p} ({len(content)} 字符)")

    if loaded:
        file_context = "\n\n---\n\n".join(loaded)
        if remaining_task:
            return f"{remaining_task}\n\n以下是相关文件内容：\n\n{file_context}"
        else:
            return f"以下是任务文件内容，请按其中的计划执行：\n\n{file_context}"

    return task


if __name__ == "__main__":
    main()
