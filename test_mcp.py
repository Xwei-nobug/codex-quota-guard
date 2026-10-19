#!/usr/bin/env python3
"""
测试验证脚本：通过子进程管道与 server.py 进行完整的 MCP 协议握手与工具调用测试。
"""

import json
import os
import subprocess
import sys

def run_test():
    server_script = os.path.join(os.path.dirname(__file__), "server.py")
    python_exe = sys.executable

    print(f"[*] 启动测试 MCP Server: {python_exe} {server_script}")
    proc = subprocess.Popen(
        [python_exe, server_script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8"
    )

    def send_request(req):
        raw = json.dumps(req, ensure_ascii=False) + "\n"
        proc.stdin.write(raw)
        proc.stdin.flush()
        line = proc.stdout.readline()
        return json.loads(line)

    try:
        # 1. initialize 握手
        print("[1] 测试 initialize 握手...")
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"}
            }
        }
        res = send_request(init_req)
        assert res.get("result", {}).get("serverInfo", {}).get("name") == "codex-quota-guard"
        print("    -> 握手成功:", res["result"]["serverInfo"])

        # 2. 发送 initialized 通知
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        # 3. tools/list 测试
        print("[2] 测试 tools/list 列出可用工具...")
        tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        res = send_request(tools_req)
        tools = res.get("result", {}).get("tools", [])
        tool_names = [t["name"] for t in tools]
        print(f"    -> 成功注册工具列表 ({len(tools)} 个): {tool_names}")
        assert "get_codex_quota" in tool_names
        assert "evaluate_task_feasibility" in tool_names

        # 4. tools/call 测试 get_codex_quota
        print("[3] 测试 tools/call -> get_codex_quota...")
        call_req_1 = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_codex_quota", "arguments": {}}
        }
        res = send_request(call_req_1)
        content_text = res.get("result", {}).get("content", [{}])[0].get("text", "")
        quota_data = json.loads(content_text)
        print("    -> 5小时剩余:", quota_data["primary_5h_window"]["remaining_percent"], "%")
        print("    -> 本周剩余:", quota_data["secondary_weekly_window"]["remaining_percent"], "%")

        # 5. tools/call 测试 evaluate_task_feasibility
        print("[4] 测试 tools/call -> evaluate_task_feasibility...")
        call_req_2 = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "evaluate_task_feasibility",
                "arguments": {
                    "task_description": "全面重构 Agent 逻辑与多文件编译"
                }
            }
        }
        res = send_request(call_req_2)
        eval_text = res.get("result", {}).get("content", [{}])[0].get("text", "")
        eval_data = json.loads(eval_text)
        print("    -> 自决策结果:", eval_data.get("decision"))
        print("    -> 行动指令:", eval_data.get("required_action"))
        print("    -> 决策消息:", eval_data.get("message"))

        print("\n[+] 所有 MCP 协议握手与工具调用测试通过！服务运行完美！")

    finally:
        proc.terminate()

if __name__ == "__main__":
    run_test()
