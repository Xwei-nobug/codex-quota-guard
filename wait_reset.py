#!/usr/bin/env python3
"""
Codex Quota Guard - 定时等待重置器 (Timer Waiter)
当配额低于 5% 时由 Codex 或用户调用，阻塞等待直到配额窗口完成重置。
重置完毕后自动退出（exit code 0），以便调用方无缝继续执行原任务。
"""

import os
import sys
import time
from pathlib import Path

# 确保 UTF-8 输出
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from quota_client import get_parsed_quota, format_duration


def main():
    print("=" * 60)
    print("      Codex 配额重置自动等待定时器")
    print("=" * 60)

    # 1. 检查当前是否真的需要等待
    quota = get_parsed_quota()
    if not quota.get("success"):
        print(f"[错误] 无法获取配额数据: {quota.get('error')}")
        sys.exit(1)

    p = quota["primary_5h_window"]
    s = quota["secondary_weekly_window"]
    p_rem = p["remaining_percent"]
    s_rem = s["remaining_percent"]
    min_rem = min(p_rem, s_rem)

    if quota.get("allowed", True) and min_rem >= 5.0:
        print(f"[提示] 当前配额充足（剩余 {min_rem}%），无需等待，直接继续！")
        sys.exit(0)

    # 2. 计算等待时长
    p_sec = p.get("reset_after_seconds") or 0
    s_sec = s.get("reset_after_seconds") or 0

    if p_rem <= s_rem:
        wait_seconds = p_sec
        bottleneck = "5小时滚动窗口"
    else:
        wait_seconds = s_sec
        bottleneck = "本周全局窗口"

    # 增加 15 秒缓冲，确保远端服务器已刷新
    total_wait = max(wait_seconds + 15, 30)
    print(f"当前剩余配额: {min_rem}%（触发 < 5% 保护机制）")
    print(f"等待重置窗口: {bottleneck}")
    print(f"预计等待时长: 约 {format_duration(total_wait)}")
    print(f"重置检查点:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + total_wait))}")
    print("-" * 60)
    print("[*] 定时器已启动，正在倒计时等待重置（按 Ctrl+C 可中断）...")

    start_time = time.time()
    end_time = start_time + total_wait

    while True:
        now = time.time()
        remaining = int(end_time - now)
        if remaining <= 0:
            break

        # 每 30 秒打印一次进度（或者最后 60 秒每 10 秒打印一次）
        step = 10 if remaining <= 60 else 30
        print(f"[{time.strftime('%H:%M:%S')}] 距离重置还剩: {format_duration(remaining)} ...")
        time.sleep(min(step, remaining))

    print("\n[*] 倒计时结束，正在向 OpenAI 查询配额恢复状态...")

    # 3. 轮询确认是否真正恢复（最多复核 3 次，间隔 10 秒）
    for retry in range(1, 4):
        new_quota = get_parsed_quota()
        if new_quota.get("success"):
            new_p_rem = new_quota["primary_5h_window"]["remaining_percent"]
            new_s_rem = new_quota["secondary_weekly_window"]["remaining_percent"]
            new_min = min(new_p_rem, new_s_rem)
            if new_min >= 5.0 and new_quota.get("allowed", True):
                print(f"[✓] 配额已成功重置！当前剩余: {new_min}%。")
                print("=" * 60)
                print("[✓] 定时等待结束，Codex 将自动继续执行当前未完成任务！")
                print("=" * 60)
                sys.exit(0)
        time.sleep(10)

    print("[提示] 等待时间已达，无论后端是否彻底同步，放行 Codex 继续尝试。")
    sys.exit(0)


if __name__ == "__main__":
    main()
