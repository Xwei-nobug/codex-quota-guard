#!/usr/bin/env python3
"""
Codex Quota Guard - 通用一键部署与集成脚本 (Universal Deployer)
支持任意电脑、任意目录、任意 Python 环境（Windows/macOS/Linux）一键部署。
"""

import os
import shutil
import sys
import time
from pathlib import Path

# 确保 UTF-8 输出
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 1. 动态自适应定位当前工程与执行环境
PROJECT_DIR = Path(__file__).resolve().parent
SERVER_SCRIPT = PROJECT_DIR / "server.py"
SKILL_TEMPLATE = PROJECT_DIR / "SKILL.md"
CLI_SCRIPT = PROJECT_DIR / "cli.py"
WAIT_SCRIPT = PROJECT_DIR / "wait_reset.py"

# 获取当前正在运行此脚本的 Python 解释器绝对路径
CURRENT_PYTHON = sys.executable or "python"

# 2. 定位 Codex 配置根目录
CODEX_DIR = Path.home() / ".codex"
CONFIG_TOML = CODEX_DIR / "config.toml"
SKILLS_DIR = CODEX_DIR / "skills"
TARGET_SKILL_DIR = SKILLS_DIR / "quota-aware-planner"
TARGET_SKILL_FILE = TARGET_SKILL_DIR / "SKILL.md"


def backup_file(path: Path) -> Path:
    """备份文件"""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak_{timestamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def deploy():
    print("=" * 65)
    print("      Codex Quota Guard 通用一键部署程序")
    print("=" * 65)
    print(f"[*] 当前项目目录: {PROJECT_DIR}")
    print(f"[*] 当前 Python:   {CURRENT_PYTHON}")
    print(f"[*] 目标 Codex:   {CODEX_DIR}")
    print("-" * 65)

    # 1. 确保 ~/.codex 目录就绪
    CODEX_DIR.mkdir(parents=True, exist_ok=True)
    auth_file = CODEX_DIR / "auth.json"
    if not auth_file.exists():
        print(f"[提示] 未检测到 {auth_file}。若尚未登录，请在终端执行 'codex login'。")

    # 2. 安装并动态渲染 Skill 文件
    print("[1/3] 正在根据当前电脑环境生成并安装 Agent 技能...")
    TARGET_SKILL_DIR.mkdir(parents=True, exist_ok=True)

    with open(SKILL_TEMPLATE, "r", encoding="utf-8") as f:
        skill_content = f.read()

    # 动态渲染当前环境的命令路径
    cli_cmd = f'"{CURRENT_PYTHON}" "{CLI_SCRIPT}"'
    wait_cmd = f'"{CURRENT_PYTHON}" "{WAIT_SCRIPT}"'
    rendered_skill = skill_content.replace("{{CLI_COMMAND}}", cli_cmd).replace("{{WAIT_COMMAND}}", wait_cmd)

    with open(TARGET_SKILL_FILE, "w", encoding="utf-8") as f:
        f.write(rendered_skill)
    print(f"    -> 技能已注入: {TARGET_SKILL_FILE}")

    # 3. 动态注册 ~/.codex/config.toml
    print("[2/3] 正在配置 ~/.codex/config.toml 注册 MCP 服务...")
    if not CONFIG_TOML.exists():
        print(f"    -> {CONFIG_TOML} 不存在，新建配置文件...")
        config_content = ""
    else:
        with open(CONFIG_TOML, "r", encoding="utf-8") as f:
            config_content = f.read()
        backup_path = backup_file(CONFIG_TOML)
        print(f"    -> 已备份原配置至: {backup_path.name}")

    # 使用 TOML 字面量单引号语法，天然支持跨平台路径（包括 Windows 反斜杠）
    mcp_section = f"""
# [Codex Quota Guard] 5小时与周限额智能自决策 MCP 服务
[mcp_servers.codex_quota]
command = '{CURRENT_PYTHON}'
args = ['{SERVER_SCRIPT}']
enabled = true
"""

    if "[mcp_servers.codex_quota]" in config_content:
        print("    -> 检测到已存在旧的 codex_quota 配置，正在自动覆写更新...")
        lines = config_content.splitlines()
        new_lines = []
        skip = False
        for line in lines:
            if "# [Codex Quota Guard]" in line:
                continue
            if line.strip() == "[mcp_servers.codex_quota]":
                skip = True
                continue
            if skip and line.strip().startswith("[") and not line.strip().startswith("[mcp_servers.codex_quota"):
                skip = False
            if not skip:
                new_lines.append(line)
        config_content = "\n".join(new_lines).rstrip() + "\n" + mcp_section
    else:
        config_content = config_content.rstrip() + "\n" + mcp_section

    with open(CONFIG_TOML, "w", encoding="utf-8") as f:
        f.write(config_content)
    print("    -> config.toml 更新成功！")

    # 4. 连通性自测
    print("[3/3] 正在自检配额接口与服务状态...")
    try:
        if str(PROJECT_DIR) not in sys.path:
            sys.path.insert(0, str(PROJECT_DIR))
        from quota_client import get_parsed_quota
        q = get_parsed_quota()
        if q.get("success"):
            p_rem = q["primary_5h_window"]["remaining_percent"]
            s_rem = q["secondary_weekly_window"]["remaining_percent"]
            print(f"    -> 验证成功！当前 5小时剩余: {p_rem}%，本周剩余: {s_rem}%。")
        else:
            print(f"    -> 提示: {q.get('error')}")
    except Exception as e:
        print(f"    -> 自检略过: {e}")

    print("=" * 65)
    print(" [✓] 部署成功！Codex 已具备自查配额与任务规划能力。")
    print("=" * 65)
    print("后续使用提示:")
    print("1. 请彻底重启 Codex 桌面客户端或新开 Codex 终端以加载配置。")
    print("2. 在 Codex 对话框中直接输入：'帮我查一下当前的 5 小时限额和本周限额'")
    print("3. 当额度低于 30% 时 Codex 会主动询问；低于 5% 时自动挂起等待重置后继续。")
    print("=" * 65)


def uninstall():
    print("=" * 65)
    print("        Codex Quota Guard 一键卸载与清理程序")
    print("=" * 65)

    if TARGET_SKILL_DIR.exists():
        shutil.rmtree(TARGET_SKILL_DIR)
        print(f"[*] 已移除安装的技能目录: {TARGET_SKILL_DIR}")

    if CONFIG_TOML.exists():
        with open(CONFIG_TOML, "r", encoding="utf-8") as f:
            content = f.read()
        if "[mcp_servers.codex_quota]" in content:
            backup_file(CONFIG_TOML)
            lines = content.splitlines()
            new_lines = []
            skip = False
            for line in lines:
                if "# [Codex Quota Guard]" in line:
                    continue
                if line.strip() == "[mcp_servers.codex_quota]":
                    skip = True
                    continue
                if skip and line.strip().startswith("[") and not line.strip().startswith("[mcp_servers.codex_quota"):
                    skip = False
                if not skip:
                    new_lines.append(line)
            with open(CONFIG_TOML, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines).strip() + "\n")
            print("[*] 已从 config.toml 中移除 codex_quota MCP 服务配置。")
    print("=" * 65)
    print("[✓] 卸载完成，环境已恢复原状。")
    print("=" * 65)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["--uninstall", "-u", "uninstall"]:
        uninstall()
    else:
        deploy()
