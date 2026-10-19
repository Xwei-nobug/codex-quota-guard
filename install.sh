#!/usr/bin/env bash
# Codex Quota Guard - macOS / Linux 一键部署脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================================="
echo "        Codex Quota Guard 一键安装部署程序 (macOS / Linux)"
echo "================================================================="

PYTHON_BIN=""
if command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
elif command -v python &>/dev/null; then
    PYTHON_BIN="python"
else
    echo "[错误] 未检测到 python3 或 python 环境，请先安装 Python 3。"
    exit 1
fi

echo "[*] 使用 Python: $($PYTHON_BIN --version)"
$PYTHON_BIN "$SCRIPT_DIR/deploy.py" "$@"
