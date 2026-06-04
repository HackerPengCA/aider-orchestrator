"""
Aider Orchestrator — 主入口
用法：python main.py --project <项目路径>
"""

import argparse
import json
import sys
from pathlib import Path

from sandbox import Sandbox
from llm_client import make_plan, analyze_result
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

    # 3. 逐步执行
    step_index = 0
    retries = 0

    while step_index < len(plan):
        step = plan[step_index]
        print(f"\n{'='*60}")
        print(f"▶ 步骤 {step['step']}/{len(plan)}: {step['description']}")
        print(f"{'='*60}")

        try:
            stdout, stderr, rc = run_step(step, sandbox)
        except Exception as e:
            stderr = str(e)
            stdout = ""
            rc = 1

        # 4. 分析结果
        remaining = plan[step_index + 1:]
        try:
            decision = analyze_result(task, remaining, step, stdout, stderr)
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
            print(f"  🔄 重试 ({retries}/{MAX_RETRIES})...")
            # 不移动 step_index，重试当前步骤
        elif action == "update_plan":
            updated = decision.get("updated_steps", [])
            if updated:
                # 替换剩余步骤
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
        task = input("📝 输入任务（输入 exit 退出）: ").strip()
        if task.lower() in ("exit", "quit", "q"):
            print("再见！")
            break
        if not task:
            continue
        run_task(task, sandbox)


if __name__ == "__main__":
    main()
