"""
Codex Quota Client - 读取与解析 OpenAI Codex 配额核心模块
支持从本地 ~/.codex/auth.json 读取凭据，直接查询官方 WHAM 使用量端点。
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional, Tuple


def get_auth_file_path() -> Path:
    """获取 ~/.codex/auth.json 的路径（适配 Windows/Linux/macOS）"""
    return Path.home() / ".codex" / "auth.json"


def load_auth_credentials() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    读取本地认证凭据
    返回: (access_token, account_id, error_message)
    """
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        return None, None, f"未找到认证文件: {auth_file}，请先在终端运行 codex login 登录"

    try:
        with open(auth_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return None, None, f"解析 {auth_file} 失败: {str(e)}"

    tokens = data.get("tokens", {})
    if not isinstance(tokens, dict):
        return None, None, "auth.json 中缺少有效的 tokens 节点"

    access_token = tokens.get("access_token")
    account_id = tokens.get("account_id")

    if not access_token:
        return None, None, "auth.json 中未找到 access_token，请重新执行 codex login"

    return access_token, account_id, None


def format_duration(seconds: Optional[int]) -> str:
    """格式化秒数为人类易读的时间字符串"""
    if seconds is None or seconds < 0:
        return "未知"
    if seconds == 0:
        return "即将重置"

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    if days > 0:
        return f"{days}天 {hours}小时"
    if hours > 0:
        return f"{hours}小时 {minutes}分钟"
    return f"{minutes}分钟"


def fetch_raw_usage(timeout: int = 10) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    直接请求 OpenAI Codex 官方使用量端点
    返回: (raw_json_data, error_message)
    """
    access_token, account_id, err = load_auth_credentials()
    if err:
        return None, err

    url = "https://chatgpt.com/backend-api/wham/usage"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "Codex/1.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json"
    }
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None, f"请求接口异常，HTTP 状态码: {resp.status}"
            content = resp.read().decode("utf-8")
            return json.loads(content), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP错误 ({e.code}): {e.reason}"
    except urllib.error.URLError as e:
        return None, f"网络请求失败: {e.reason}"
    except Exception as e:
        return None, f"未知错误: {str(e)}"


def get_parsed_quota() -> Dict[str, Any]:
    """
    获取结构化、格式化后的配额信息
    """
    raw_data, err = fetch_raw_usage()
    if err:
        return {
            "success": False,
            "error": err,
            "allowed": False
        }

    plan_type = raw_data.get("plan_type", "unknown")
    rate_limit = raw_data.get("rate_limit", {})
    allowed = rate_limit.get("allowed", True)
    limit_reached = rate_limit.get("limit_reached", False)
    
    primary = rate_limit.get("primary_window", {})
    secondary = rate_limit.get("secondary_window", {})

    # 5 小时主要窗口（18000 秒）
    p_used = float(primary.get("used_percent", 0.0))
    p_rem = round(max(0.0, 100.0 - p_used), 2)
    p_reset_sec = primary.get("reset_after_seconds")
    p_reset_at = primary.get("reset_at")

    # 7 天次要窗口（604800 秒）
    s_used = float(secondary.get("used_percent", 0.0))
    s_rem = round(max(0.0, 100.0 - s_used), 2)
    s_reset_sec = secondary.get("reset_after_seconds")
    s_reset_at = secondary.get("reset_at")

    # 状态评估
    def evaluate_status(remaining: float) -> str:
        if remaining <= 0:
            return "EXHAUSTED"
        if remaining < 15:
            return "CRITICAL"
        if remaining < 30:
            return "WARNING"
        return "HEALTHY"

    # 即时重置权益（如有）
    reset_credits = raw_data.get("rate_limit_reset_credits", {})
    available_resets = reset_credits.get("available_count", 0)

    return {
        "success": True,
        "allowed": allowed and not limit_reached,
        "plan_type": plan_type,
        "email": raw_data.get("email"),
        "primary_5h_window": {
            "name": "5小时滚动限额",
            "used_percent": p_used,
            "remaining_percent": p_rem,
            "reset_after_seconds": p_reset_sec,
            "reset_in": format_duration(p_reset_sec),
            "reset_timestamp": p_reset_at,
            "status": evaluate_status(p_rem)
        },
        "secondary_weekly_window": {
            "name": "本周全局限额",
            "used_percent": s_used,
            "remaining_percent": s_rem,
            "reset_after_seconds": s_reset_sec,
            "reset_in": format_duration(s_reset_sec),
            "reset_timestamp": s_reset_at,
            "status": evaluate_status(s_rem)
        },
        "banked_reset_credits": available_resets
    }


def evaluate_task_plan(task_description: str = "") -> Dict[str, Any]:
    """
    智能决策引擎：
    - < 5%: 必须设置定时器，等待重置（约需要等待特定时长），重置后自动继续当前任务。
    - 5% ~ 30%: 必须主动询问用户如何执行任务（提供选项）。
    - >= 30%: 充沛放行，全速自主执行，不打扰用户。
    """
    quota = get_parsed_quota()
    if not quota.get("success"):
        return {
            "decision": "UNKNOWN",
            "message": f"未能读取配额 ({quota.get('error')})，请谨慎执行。",
            "required_action": "PROCEED"
        }

    p_rem = quota["primary_5h_window"]["remaining_percent"]
    s_rem = quota["secondary_weekly_window"]["remaining_percent"]
    min_rem = min(p_rem, s_rem)

    p_reset_sec = quota["primary_5h_window"]["reset_after_seconds"] or 0
    s_reset_sec = quota["secondary_weekly_window"]["reset_after_seconds"] or 0
    p_reset_in = quota["primary_5h_window"]["reset_in"]
    s_reset_in = quota["secondary_weekly_window"]["reset_in"]

    # 判断哪一个是当前瓶颈窗口
    is_primary_bottleneck = (p_rem <= s_rem)
    wait_sec = p_reset_sec if is_primary_bottleneck else s_reset_sec
    wait_str = p_reset_in if is_primary_bottleneck else s_reset_in
    bottleneck_name = "5小时窗口" if is_primary_bottleneck else "周窗口"

    # 动态获取当前运行环境的 Python 路径与伴生脚本路径（确保任意机器通用）
    python_cmd = sys.executable or "python"
    script_dir = Path(__file__).resolve().parent
    wait_script_path = str(script_dir / "wait_reset.py")
    wait_cmd = f'"{python_cmd}" "{wait_script_path}"'

    # 1. 额度低于 5% 或已受限：设置定时器等待重置，重置后自动继续
    if not quota["allowed"] or min_rem < 5.0:
        return {
            "decision": "WAIT_FOR_RESET",
            "remaining_percent": min_rem,
            "wait_seconds": wait_sec + 15,
            "wait_time_readable": wait_str,
            "bottleneck": bottleneck_name,
            "message": f"[WAIT] 当前配额仅剩 {min_rem}%（已低于 5% 临界线）。为防任务中途中断，必须设置定时器等待 {bottleneck_name} 自然时间重置（还需约 {wait_str}），重置后自动恢复并继续执行当前任务。【严格禁令：严禁使用用户的任何即时重置点/重置额度】",
            "required_action": "SET_TIMER_AND_RESUME",
            "reset_credits_policy": "STRICTLY_PROHIBITED (严禁使用任何即时重置额度/重置点)",
            "recommended_command": wait_cmd,
            "instructions_for_codex": (
                f"1. 立即向用户说明：当前配额为 {min_rem}%（低于 5%），即将设置定时器等待自然重置（约需等待 {wait_str}）。\n"
                f"2. 【绝对红线】：严禁以任何形式使用、消耗或建议用户使用任何即时重置额度/重置点（Banked Reset Credits），必须等待时间自然重置！\n"
                f"3. 在终端执行等待脚本：{wait_cmd}（或设置等待定时器 {wait_sec} 秒）。\n"
                f"4. 定时器结束且配额自然恢复后，重新核验配额，并自动继续执行当前未完成的任务！"
            ),
            "quota_snapshot": quota
        }

    # 2. 额度低于 30%（5% ~ 30%）：必须询问用户如何执行
    if min_rem < 30.0:
        return {
            "decision": "ASK_USER",
            "remaining_percent": min_rem,
            "reset_in": wait_str,
            "bottleneck": bottleneck_name,
            "message": f"[ASK] 当前配额剩余 {min_rem}%（已低于 30% 预警线，距 {bottleneck_name} 自然重置还剩 {wait_str}）。必须暂停自主盲目推进，主动询问用户期望如何执行当前任务。【严格禁令：严禁使用用户的任何即时重置点/重置额度】",
            "required_action": "PROMPT_USER_FOR_INSTRUCTION",
            "reset_credits_policy": "STRICTLY_PROHIBITED (严禁使用任何即时重置额度/重置点)",
            "instructions_for_codex": (
                f"必须向用户主动报告配额状态（剩余 {min_rem}%，自然重置还需约 {wait_str}），并请用户选择后续执行方案：\n"
                f"（注意：严禁使用任何即时重置额度/重置点，只能等待自然重置或按以下方案推进）\n"
                f"1. 方案 A: 仅修改核心代码文件（精简上下文与推理，最大限度节约额度）\n"
                f"2. 方案 B: 将任务严格拆分为微小原子步骤，每完成一步向您汇报确认一次\n"
                f"3. 方案 C: 保持原计划全速执行\n"
                f"4. 方案 D: 暂缓任务，等待自然时间重置后再继续"
            ),
            "quota_snapshot": quota
        }

    # 3. 额度 >= 30%：充沛放行，不打扰用户
    return {
        "decision": "PROCEED",
        "remaining_percent": min_rem,
        "message": f"[OK] 配额充足（5小时剩余 {p_rem}%，本周剩余 {s_rem}%）。无需打扰用户，全速自主推进当前任务。【严禁使用任何即时重置点】",
        "required_action": "EXECUTE_NORMALLY",
        "reset_credits_policy": "STRICTLY_PROHIBITED (严禁使用任何即时重置额度/重置点)",
        "instructions_for_codex": "配额充裕（>= 30%），无需特意询问用户，全速自主执行任务规划与代码实现。注意：严禁动用任何重置点。",
        "quota_snapshot": quota
    }
