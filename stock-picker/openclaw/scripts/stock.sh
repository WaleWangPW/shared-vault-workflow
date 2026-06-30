#!/usr/bin/env bash
# stock.sh —— openclaw stock-picker skill 入口
# 用法：bash stock.sh <指令> [参数...]
set -euo pipefail

STOCK_DIR="${STOCK_PICKER_DIR:-/Users/weihongwang/shared-vault-workflow/stock-picker}"

if [ ! -f "$STOCK_DIR/cmd.py" ]; then
    echo "❌ 找不到股票脚本：$STOCK_DIR/cmd.py"
    echo "   请检查 STOCK_PICKER_DIR 环境变量或重新运行 install_openclaw_skill.sh"
    exit 1
fi

# 加载 Python 虚拟环境（如有）
if [ -f "$STOCK_DIR/.venv/bin/activate" ]; then
    # shellcheck disable=SC1090
    source "$STOCK_DIR/.venv/bin/activate"
fi

exec python3 -u "$STOCK_DIR/cmd.py" "$@"
