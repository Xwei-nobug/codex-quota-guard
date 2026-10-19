#!/usr/bin/env python3
"""
Codex Quota Guard - MCP Server (Model Context Protocol)
零第三方依赖，纯 Python 3 原生标准库实现的 MCP stdio 服务器。
供 Codex 等 Agent 在规划或执行任务时自动化自查 5 小时限额与周限额，做出智能自决策。
"""

import json
import os
import sys
import traceback
from pathlib import Path

# 使用官方推荐的 reconfigure 确保 Windows 下 stdin/stdout/stderr 均为 UTF-8
try:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 引入核心配额解析客户端
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from quota_client import get_parsed_quota, evaluate_task_plan

SERVER_NAME = "codex-quota-guard"
SERVER_VERSION = "1.0.0"

# 调试日志文件
DEBUG_LOG_FILE = current_dir / "mcp_traffic.log"

def file_log(msg: str):
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{SERVER_NAME}] {msg}\n")
    except Exception:
        pass

def log_debug(msg: str):
    """日志统一输出到 stderr 和本地文件，绝不污染 stdout（stdio MCP 协议要求）"""
    file_log(msg)
    try:
        sys.stderr.write(f"[{SERVER_NAME}] {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass

TOOLS_METADATA = [
    {
        "name": "get_codex_quota",
        "description": (
            "获取当前 OpenAI Codex 账号的 5 小时滚动限额和本周全局限额详情。"
            "返回当前使用百分比、剩余百分比、重置倒计时（小时/分钟）、套餐类型以及可用即时重置点。"
            "当需要了解当前算力健康度时调用。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "evaluate_task_feasibility",
        "description": (
            "【任务规划核心自决策工具】根据当前 5 小时与周度剩余配额，自动决定任务执行策略。"
            "【绝对红线：严禁以任何方式使用、消耗或建议使用用户的即时重置额度/重置点，必须等待自然时间重置】"
            "1. 额度 < 5%：返回 WAIT_FOR_RESET，指示 Codex 设置定时器等待自然时间重置，重置后自动继续执行当前任务；"
            "2. 5% <= 额度 < 30%：返回 ASK_USER，指示 Codex 暂停盲目执行，主动向用户汇报并询问用户希望如何执行；"
            "3. 额度 >= 30%：返回 PROCEED，配额充裕，全速自主推进，不打扰用户。"
            "Codex 在开始任务规划、多步操作或长流程 Agent 任务前应首先调用此工具自检。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_description": {
                    "type": "string",
                    "description": "当前计划执行的任务简要描述（可选，如：重构登录认证模块）"
                }
            },
            "required": []
        }
    }
]


def handle_initialize(req_id, params: dict) -> dict:
    client_proto = params.get("protocolVersion", "2024-11-05")
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": client_proto,
            "capabilities": {
                "tools": {
                    "listChanged": True
                }
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION
            }
        }
    }


def handle_tools_list(req_id, params: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "tools": TOOLS_METADATA
        }
    }


def handle_tools_call(req_id, params: dict) -> dict:
    tool_name = params.get("name")
    args = params.get("arguments", {})

    log_debug(f"Tool called: {tool_name} with args: {args}")

    if tool_name == "get_codex_quota":
        quota_data = get_parsed_quota()
        text_content = json.dumps(quota_data, indent=2, ensure_ascii=False)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": text_content
                    }
                ],
                "isError": not quota_data.get("success", False)
            }
        }

    elif tool_name == "evaluate_task_feasibility":
        description = args.get("task_description", "")
        plan = evaluate_task_plan(description)
        text_content = json.dumps(plan, indent=2, ensure_ascii=False)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": text_content
                    }
                ],
                "isError": False
            }
        }

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"未找到对应工具: {tool_name}"
            }
        }


def handle_ping(req_id, params: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {}
    }


def main():
    log_debug("Codex Quota Guard MCP Server started successfully.")

    # 使用 readline 代替 for line in sys.stdin，避免在管道传输中产生缓冲停滞
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                log_debug("Stdin reached EOF, server exiting gracefully.")
                break

            line_str = line.strip()
            if not line_str:
                continue

            file_log(f"RECV: {line_str}")

            try:
                req = json.loads(line_str)
            except json.JSONDecodeError as e:
                log_debug(f"JSON decode error: {e}")
                continue

            method = req.get("method")
            req_id = req.get("id")
            params = req.get("params", {})

            # 处理通知（无需应答）
            if method == "notifications/initialized":
                log_debug("Handshake completed: notifications/initialized received.")
                continue

            response = None
            if method == "initialize":
                response = handle_initialize(req_id, params)
            elif method == "tools/list":
                response = handle_tools_list(req_id, params)
            elif method == "tools/call":
                response = handle_tools_call(req_id, params)
            elif method == "ping":
                response = handle_ping(req_id, params)
            else:
                if req_id is not None:
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method not found: {method}"
                        }
                    }

            if response:
                out_str = json.dumps(response, ensure_ascii=False)
                file_log(f"SEND: {out_str}")
                sys.stdout.write(out_str + "\n")
                sys.stdout.flush()

        except Exception as e:
            log_debug(f"Exception in main loop: {traceback.format_exc()}")
            break


if __name__ == "__main__":
    main()
