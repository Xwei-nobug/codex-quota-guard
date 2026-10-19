#!/usr/bin/env python3
"""
Codex Quota Guard - 命令行直接查询工具 (CLI)
供用户在终端随时查看当前 Codex 5小时和周度配额状况。
"""

import os
import sys
from pathlib import Path

# 确保 UTF-8 编码
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from quota_client import get_parsed_quota, evaluate_task_plan

def render_progress_bar(percent: float, width: int = 24) -> str:
    """渲染纯文本进度条"""
    filled_len = int(round(width * percent / 100))
    bar = "=" * filled_len + "-" * (width - filled_len)
    return f"[{bar}] {percent:>5.1f}%"

def main():
    print("=" * 60)
    print("           Codex 实时配额与任务决策监测台")
    print("=" * 60)

    quota = get_parsed_quota()
    if not quota.get("success"):
        print(f"[错误] 无法获取配额: {quota.get('error')}")
        sys.exit(1)

    plan = quota.get("plan_type", "未知").upper()
    email = quota.get("email", "未知")
    allowed = quota.get("allowed", True)
    credits = quota.get("banked_reset_credits", 0)

    print(f"账号邮箱:   {email}")
    print(f"订阅套餐:   {plan} Plan")
    print(f"服务状态:   {'正常可用 (Allowed)' if allowed else '受到限制 (Restricted)'}")
    print(f"即时重置点: {credits} 个可用")
    print("-" * 60)

    # 5 小时窗口
    p = quota["primary_5h_window"]
    print(f"[1] 5 小时滚动窗口 (短周期):")
    print(f"    使用进度:   {render_progress_bar(p['used_percent'])}")
    print(f"    剩余可用:   {p['remaining_percent']}%")
    print(f"    重置倒计时: 约 {p['reset_in']}")
    print(f"    健康状态:   {p['status']}")
    print()

    # 周窗口
    s = quota["secondary_weekly_window"]
    print(f"[2] 本周全局窗口 (长周期):")
    print(f"    使用进度:   {render_progress_bar(s['used_percent'])}")
    print(f"    剩余可用:   {s['remaining_percent']}%")
    print(f"    重置倒计时: 约 {s['reset_in']}")
    print(f"    健康状态:   {s['status']}")
    print("=" * 60)

    # 任务执行建议示例
    eval_result = evaluate_task_plan("常规任务自检")
    print(f"自决策状态:   {eval_result['decision']} ({eval_result.get('required_action', 'N/A')})")
    print(f"执行指导:     {eval_result['message']}")
    print("=" * 60)

if __name__ == "__main__":
    main()
