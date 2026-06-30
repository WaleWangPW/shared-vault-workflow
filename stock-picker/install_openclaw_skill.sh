#!/usr/bin/env bash
# ============================================================
# 把股票助手技能安装到 openclaw feishu-agent
# 运行：cd stock-picker && bash install_openclaw_skill.sh
# ============================================================
set -euo pipefail

STOCK_DIR="$(cd "$(dirname "$0")" && pwd)"
OPENCLAW_DIR="$HOME/.openclaw"
AGENT_SKILLS="$OPENCLAW_DIR/agents/feishu-agent/workspace/skills"

echo "=================================================="
echo "  股票助手 openclaw 技能安装"
echo "  脚本目录: $STOCK_DIR"
echo "=================================================="
echo ""

# ── 1. 检查 openclaw ────────────────────────────────────────
if [ ! -d "$OPENCLAW_DIR" ]; then
    echo "❌ 未找到 ~/.openclaw，请先确认 openclaw 已安装"
    exit 1
fi

if [ ! -d "$AGENT_SKILLS" ]; then
    echo "❌ 未找到 feishu-agent skills 目录：$AGENT_SKILLS"
    echo "   请检查 openclaw 中 feishu-agent 是否已存在"
    exit 1
fi
echo "✅ openclaw feishu-agent 已找到"

# ── 2. 停止 feishu_handler.py（如正在运行）──────────────────
LAUNCH_DIR="$HOME/Library/LaunchAgents"
FEISHU_PLIST="$LAUNCH_DIR/com.stockpicker.feishu.plist"

if [ -f "$FEISHU_PLIST" ]; then
    echo ""
    echo ">>> 停止独立 feishu_handler 服务（与 openclaw 冲突）..."
    launchctl unload "$FEISHU_PLIST" 2>/dev/null || true
    rm -f "$FEISHU_PLIST"
    echo "✅ com.stockpicker.feishu 已停止并移除"
fi

# 同时 kill 可能仍在运行的进程
pkill -f "feishu_handler.py" 2>/dev/null && echo "✅ feishu_handler.py 进程已终止" || true

# ── 3. 安装 stock-picker skill ──────────────────────────────
SKILL_DEST="$AGENT_SKILLS/stock-picker"
mkdir -p "$SKILL_DEST"

cp "$STOCK_DIR/openclaw/SKILL.md" "$SKILL_DEST/SKILL.md"

# 把 SKILL.md 中的占位路径替换为实际绝对路径（避免 Node.js 不展开 ~）
sed -i '' "s|~/shared-vault-workflow/stock-picker|$STOCK_DIR|g" "$SKILL_DEST/SKILL.md" 2>/dev/null \
  || sed -i "s|~/shared-vault-workflow/stock-picker|$STOCK_DIR|g" "$SKILL_DEST/SKILL.md"

# 写入 STOCK_PICKER_DIR 路径，供 openclaw shell 环境使用
cat > "$SKILL_DEST/env.sh" <<ENV
#!/usr/bin/env bash
# 股票助手路径（供 openclaw 执行 Python 脚本时使用）
export STOCK_PICKER_DIR="$STOCK_DIR"
ENV

echo ""
echo "✅ stock-picker skill 已安装到："
echo "   $SKILL_DEST"

# ── 4. 检查 .env 是否已配置 ─────────────────────────────────
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
        echo "⚠️  .env 中 FEISHU_APP_ID 为空，请填写后方可推送"
    fi
fi

# ── 5. 保留定时任务（日报 + 监控，无 WebSocket 冲突）─────────
echo ""
echo ">>> 检查定时任务服务..."

DAILY_PLIST="$LAUNCH_DIR/com.stockpicker.daily.plist"
MONITOR_PLIST="$LAUNCH_DIR/com.stockpicker.monitor.plist"

if [ -f "$DAILY_PLIST" ]; then
    echo "✅ com.stockpicker.daily 已存在（工作日 08:30 日报）"
else
    echo "⚠️  com.stockpicker.daily 不存在，如需自动日报请先运行 install_mac.sh"
fi

if [ -f "$MONITOR_PLIST" ]; then
    echo "✅ com.stockpicker.monitor 已存在（盘中监控）"
fi

# ── 6. 重启 openclaw feishu-agent ───────────────────────────
echo ""
echo ">>> 重启 openclaw feishu-agent 以加载新技能..."

# 尝试通过 launchctl 重启（openclaw 通常注册为 launchd 服务）
OC_PLIST=$(ls "$HOME/Library/LaunchAgents/"*.openclaw*.plist 2>/dev/null | head -1 || true)
if [ -n "$OC_PLIST" ]; then
    launchctl unload "$OC_PLIST" 2>/dev/null || true
    sleep 1
    launchctl load -w "$OC_PLIST" 2>/dev/null || true
    echo "✅ openclaw 已通过 launchctl 重启"
elif command -v pm2 &>/dev/null && pm2 list 2>/dev/null | grep -q "openclaw"; then
    pm2 restart openclaw 2>/dev/null || true
    echo "✅ openclaw 已通过 pm2 重启"
else
    echo "ℹ️  请手动重启 openclaw 以加载 stock-picker 技能："
    echo "   pkill -f openclaw && openclaw start  # 或你平时的启动方式"
fi

# ── 完成 ─────────────────────────────────────────────────────
echo ""
echo "=================================================="
echo "  ✅ 安装完成！"
echo "=================================================="
echo ""
echo "现在发送以下消息给飞书 openclaw agent 测试："
echo "  帮助          → 查看所有指令"
echo "  诊断          → 验证数据源和凭证"
echo "  持仓          → 查看当前持仓"
echo "  选股 A        → 扫描 A 股"
echo ""
echo "如果 openclaw 不响应，检查 skill 路径："
echo "  ls $SKILL_DEST"
echo ""
echo "查看 openclaw 日志："
OC_LOG=$(ls "$OPENCLAW_DIR/logs/"*.log 2>/dev/null | tail -1 || echo "~/.openclaw/logs/")
echo "  tail -f $OC_LOG"
