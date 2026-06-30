#!/usr/bin/env bash
# ============================================================
# 把股票助手技能安装到 openclaw ai-news-agent
# 运行：cd stock-picker && bash install_openclaw_skill.sh
# ============================================================
set -euo pipefail

STOCK_DIR="$(cd "$(dirname "$0")" && pwd)"
OPENCLAW_DIR="$HOME/.openclaw"
AGENT_SKILLS="$OPENCLAW_DIR/agents/ai-news-agent/workspace/skills"

echo "=================================================="
echo "  股票助手 openclaw 技能安装（ai-news-agent）"
echo "  脚本目录: $STOCK_DIR"
echo "=================================================="
echo ""

# ── 1. 检查 openclaw ai-news-agent ──────────────────────────
if [ ! -d "$OPENCLAW_DIR" ]; then
    echo "❌ 未找到 ~/.openclaw，请先确认 openclaw 已安装"
    exit 1
fi

if [ ! -d "$AGENT_SKILLS" ]; then
    echo "❌ 未找到 ai-news-agent skills 目录：$AGENT_SKILLS"
    exit 1
fi
echo "✅ openclaw ai-news-agent 已找到"

# ── 2. 停止 feishu_handler.py（如还在运行）─────────────────
LAUNCH_DIR="$HOME/Library/LaunchAgents"
FEISHU_PLIST="$LAUNCH_DIR/com.stockpicker.feishu.plist"

if [ -f "$FEISHU_PLIST" ]; then
    echo ""
    echo ">>> 停止独立 feishu_handler 服务（与 openclaw 冲突）..."
    launchctl unload "$FEISHU_PLIST" 2>/dev/null || true
    rm -f "$FEISHU_PLIST"
    echo "✅ com.stockpicker.feishu 已停止并移除"
fi
pkill -f "feishu_handler.py" 2>/dev/null && echo "✅ feishu_handler.py 进程已终止" || true

# ── 3. 安装 stock-picker skill ──────────────────────────────
SKILL_DEST="$AGENT_SKILLS/stock-picker"
mkdir -p "$SKILL_DEST/scripts"

# 复制 SKILL.md
cp "$STOCK_DIR/openclaw/SKILL.md" "$SKILL_DEST/SKILL.md"

# 复制 shell 包装脚本
cp "$STOCK_DIR/openclaw/scripts/stock.sh" "$SKILL_DEST/scripts/stock.sh"
chmod +x "$SKILL_DEST/scripts/stock.sh"

# 把 stock.sh 中的默认路径替换为实际绝对路径
sed -i '' "s|/Users/weihongwang/shared-vault-workflow/stock-picker|$STOCK_DIR|g" \
    "$SKILL_DEST/scripts/stock.sh" 2>/dev/null \
  || sed -i "s|/Users/weihongwang/shared-vault-workflow/stock-picker|$STOCK_DIR|g" \
    "$SKILL_DEST/scripts/stock.sh"

echo ""
echo "✅ stock-picker skill 已安装到："
echo "   $SKILL_DEST"
echo "   $SKILL_DEST/scripts/stock.sh"

# 快速验证脚本可执行
echo ""
echo ">>> 验证 Python 脚本可调用..."
STOCK_PICKER_DIR="$STOCK_DIR" bash "$SKILL_DEST/scripts/stock.sh" 帮助 2>&1 | head -5 \
  && echo "✅ stock.sh 验证通过" \
  || echo "⚠️  验证失败，请检查 Python 依赖"

# ── 4. 检查 .env ─────────────────────────────────────────────
if [ ! -f "$STOCK_DIR/.env" ]; then
    echo ""
    echo "⚠️  未找到 .env，请先配置凭证："
    echo "    open $STOCK_DIR/.env"
else
    # shellcheck disable=SC1090
    source "$STOCK_DIR/.env" 2>/dev/null || true
    if [ -n "${FEISHU_APP_ID:-}" ]; then
        echo "✅ .env 已配置 (APP_ID=${FEISHU_APP_ID:0:8}...)"
    else
        echo "⚠️  .env 中 FEISHU_APP_ID 为空，请填写"
    fi
fi

# ── 5. 检查定时任务 ──────────────────────────────────────────
echo ""
echo ">>> 检查定时任务服务..."
[ -f "$LAUNCH_DIR/com.stockpicker.daily.plist" ] \
  && echo "✅ com.stockpicker.daily 已存在（工作日 08:30 日报）" \
  || echo "⚠️  com.stockpicker.daily 不存在，如需自动日报请先运行 install_mac.sh"
[ -f "$LAUNCH_DIR/com.stockpicker.monitor.plist" ] \
  && echo "✅ com.stockpicker.monitor 已存在（盘中监控）" || true

# ── 6. 重启 openclaw ai-news-agent ──────────────────────────
echo ""
echo ">>> 重启 openclaw 以加载新技能..."

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
    echo "ℹ️  请手动重启 openclaw ai-news-agent 以加载技能"
fi

# ── 完成 ─────────────────────────────────────────────────────
echo ""
echo "=================================================="
echo "  ✅ 安装完成！"
echo "=================================================="
echo ""
echo "发送以下消息给飞书 AI资讯助手 测试股票技能："
echo "  帮助           → 股票指令菜单"
echo "  诊断           → 验证数据源和凭证"
echo "  持仓           → 查看当前持仓"
echo "  查 688008      → 查单股买点"
echo "  选股 A         → 扫描 A 股"
echo ""
echo "技能路径：$SKILL_DEST"
