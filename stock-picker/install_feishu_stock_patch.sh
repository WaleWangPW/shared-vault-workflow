#!/usr/bin/env bash
# ============================================================
# 把 stock-picker 股票指令注入 openclaw ai-news-agent 的
# rating-server.py（飞书消息处理器）。
#
# 运行：cd stock-picker && bash install_feishu_stock_patch.sh
# 仅重启：bash install_feishu_stock_patch.sh --restart-only
# ============================================================
set -euo pipefail

STOCK_DIR="$(cd "$(dirname "$0")" && pwd)"
RS_PATH="$HOME/.openclaw/agents/ai-news-agent/workspace/scripts/rating-server.py"

_restart_openclaw() {
    local OC_PLIST
    OC_PLIST=$(ls "$HOME/Library/LaunchAgents/"*openclaw*.plist 2>/dev/null | head -1 || true)
    if [ -n "$OC_PLIST" ]; then
        launchctl unload "$OC_PLIST" 2>/dev/null || true
        sleep 1
        launchctl load -w "$OC_PLIST" 2>/dev/null || true
        echo "✅ openclaw 已通过 launchctl 重启"
    elif command -v pm2 &>/dev/null && pm2 list 2>/dev/null | grep -q "openclaw"; then
        pm2 restart openclaw 2>/dev/null || true
        echo "✅ openclaw 已通过 pm2 重启"
    else
        echo "ℹ️  请手动重启 openclaw ai-news-agent："
        echo "   launchctl unload ~/Library/LaunchAgents/*openclaw*.plist"
        echo "   launchctl load   ~/Library/LaunchAgents/*openclaw*.plist"
    fi
}

echo "=================================================="
echo "  stock-picker → rating-server.py 集成补丁"
echo "  stock 目录: $STOCK_DIR"
echo "=================================================="
echo ""

# ── 仅重启模式 ──────────────────────────────────────────────
if [ "${1:-}" = "--restart-only" ]; then
    echo ">>> 仅重启 openclaw ai-news-agent..."
    _restart_openclaw
    exit 0
fi

# ── 1. 检查依赖 ──────────────────────────────────────────────
if [ ! -f "$RS_PATH" ]; then
    echo "❌ 未找到 rating-server.py："
    echo "   $RS_PATH"
    echo "   请确认 openclaw ai-news-agent 已正确安装"
    exit 1
fi
echo "✅ 找到 rating-server.py"

if [ ! -f "$STOCK_DIR/cmd.py" ]; then
    echo "❌ 未找到 stock-picker/cmd.py"
    exit 1
fi
echo "✅ 找到 cmd.py"

# ── 2. 选择 Python 解释器 ────────────────────────────────────
PYTHON="python3"
if [ -f "$STOCK_DIR/.venv/bin/python3" ]; then
    PYTHON="$STOCK_DIR/.venv/bin/python3"
    echo "✅ 使用虚拟环境: $PYTHON"
fi

# ── 3. 检查 .env ─────────────────────────────────────────────
if [ ! -f "$STOCK_DIR/.env" ]; then
    echo "⚠️  未找到 .env，请先配置凭证："
    echo "    open $STOCK_DIR/.env"
else
    # shellcheck disable=SC1090
    source "$STOCK_DIR/.env" 2>/dev/null || true
    if [ -n "${FEISHU_APP_ID:-}" ]; then
        echo "✅ .env 已配置 (FEISHU_APP_ID=${FEISHU_APP_ID:0:8}...)"
    else
        echo "⚠️  .env 中 FEISHU_APP_ID 为空，请填写后再测试"
    fi
fi

# ── 4. 验证 cmd.py 可调用 ────────────────────────────────────
echo ""
echo ">>> 验证 stock-picker/cmd.py..."
if (cd "$STOCK_DIR" && $PYTHON cmd.py 帮助 2>&1 | head -3); then
    echo "✅ cmd.py 验证通过"
else
    echo "⚠️  cmd.py 返回错误，请检查依赖：pip install -r requirements.txt"
fi

# ── 5. 打补丁 ────────────────────────────────────────────────
echo ""
echo ">>> 打补丁到 rating-server.py..."
$PYTHON "$STOCK_DIR/patch_rating_server.py" "$RS_PATH"

# ── 6. 重启 openclaw ─────────────────────────────────────────
echo ""
echo ">>> 重启 openclaw ai-news-agent..."
_restart_openclaw

# ── 完成 ─────────────────────────────────────────────────────
echo ""
echo "=================================================="
echo "  ✅ 安装完成！"
echo "=================================================="
echo ""
echo "发送以下消息给飞书 AI资讯助手 测试股票功能："
echo "  帮助           → 股票指令菜单"
echo "  诊断           → 验证数据源和凭证"
echo "  持仓           → 查看当前持仓"
echo "  查 688008      → 查单股买点"
echo "  选股 A         → 扫描 A 股"
echo ""
echo "如需回滚：将 rating-server.py.bak_*.py 还原后重启 openclaw"
