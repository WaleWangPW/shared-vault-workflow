#!/usr/bin/env bash
# ============================================================
# 股票助手 Mac Mini 一键安装脚本
# 运行：cd stock-picker && bash install_mac.sh
# ============================================================
set -euo pipefail

STOCK_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
PYTHON3="$(command -v python3 || true)"

echo "=================================================="
echo "  股票助手 Mac Mini 安装"
echo "  安装路径: $STOCK_DIR"
echo "=================================================="
echo ""

# ── 检查 Python ───────────────────────────────────────────
if [ -z "$PYTHON3" ]; then
    echo "❌ 未找到 python3，请先安装："
    echo "   brew install python3"
    exit 1
fi
echo "✅ Python: $PYTHON3 ($($PYTHON3 --version))"

# ── 安装依赖 ─────────────────────────────────────────────
echo ""
echo ">>> 安装 Python 依赖..."
$PYTHON3 -m pip install -r "$STOCK_DIR/requirements.txt" -q --break-system-packages 2>/dev/null \
    || $PYTHON3 -m pip install -r "$STOCK_DIR/requirements.txt" -q
echo "✅ 依赖安装完成"

# ── 创建 .env（首次） ────────────────────────────────────
if [ ! -f "$STOCK_DIR/.env" ]; then
    echo ""
    echo ">>> 未找到 .env，正在创建模板..."
    cat > "$STOCK_DIR/.env" <<'ENV'
# ===== 飞书应用凭证（必填） =====
# 开放平台 → 应用 → 凭证与基础信息
FEISHU_APP_ID=
FEISHU_APP_SECRET=

# 接收消息的飞书群 chat_id（oc_xxx 格式）
FEISHU_CHAT_ID=

# Newsagent 机器人的 open_id（ou_xxx 格式，可选）
NEWSAGENT_CHAT_ID=

# ===== Tushare Token（A股深度选股必填） =====
# https://tushare.pro/register
TUSHARE_TOKEN=

# ===== 飞书自定义机器人 Webhook（可选，与 App API 二选一） =====
# FEISHU_WEBHOOK_URL=
ENV
    echo ""
    echo "⚠️  已创建 .env 模板，请填写凭证后重新运行本脚本："
    echo "    open $STOCK_DIR/.env"
    exit 0
fi

# 检查必填项
source "$STOCK_DIR/.env" 2>/dev/null || true
if [ -z "${FEISHU_APP_ID:-}" ] || [ -z "${FEISHU_APP_SECRET:-}" ]; then
    echo "❌ .env 中 FEISHU_APP_ID 或 FEISHU_APP_SECRET 为空，请先填写"
    echo "    open $STOCK_DIR/.env"
    exit 1
fi
echo "✅ .env 已配置 (APP_ID=${FEISHU_APP_ID:0:8}...)"

# ── 创建日志目录 ─────────────────────────────────────────
mkdir -p "$STOCK_DIR/logs"

# ── 生成 launchd plist ───────────────────────────────────
mkdir -p "$LAUNCH_DIR"

echo ""
echo ">>> 配置 launchd 服务..."

# 1. feishu_handler —— 开机自启 + 崩溃自动重启
cat > "$LAUNCH_DIR/com.stockpicker.feishu.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.stockpicker.feishu</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON3</string>
        <string>-u</string>
        <string>$STOCK_DIR/feishu_handler.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$STOCK_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>30</integer>
    <key>StandardOutPath</key>
    <string>$STOCK_DIR/logs/feishu.log</string>
    <key>StandardErrorPath</key>
    <string>$STOCK_DIR/logs/feishu.log</string>
</dict>
</plist>
PLIST

# 2. run_daily —— 工作日 08:30 自动执行
cat > "$LAUNCH_DIR/com.stockpicker.daily.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.stockpicker.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON3</string>
        <string>-u</string>
        <string>$STOCK_DIR/run_daily.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$STOCK_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>30</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>$STOCK_DIR/logs/daily.log</string>
    <key>StandardErrorPath</key>
    <string>$STOCK_DIR/logs/daily.log</string>
</dict>
</plist>
PLIST

# 3. realtime_monitor —— 工作日 09:20 启动，15:05 停止
cat > "$LAUNCH_DIR/com.stockpicker.monitor.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.stockpicker.monitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON3</string>
        <string>-u</string>
        <string>$STOCK_DIR/realtime_monitor.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$STOCK_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>$STOCK_DIR/logs/monitor.log</string>
    <key>StandardErrorPath</key>
    <string>$STOCK_DIR/logs/monitor.log</string>
</dict>
</plist>
PLIST

# ── 加载服务 ─────────────────────────────────────────────
for label in com.stockpicker.feishu com.stockpicker.daily com.stockpicker.monitor; do
    launchctl unload "$LAUNCH_DIR/${label}.plist" 2>/dev/null || true
    launchctl load -w "$LAUNCH_DIR/${label}.plist"
    echo "  ✅ $label 已加载"
done

# ── 完成 ─────────────────────────────────────────────────
echo ""
echo "=================================================="
echo "  ✅ 安装完成！"
echo "=================================================="
echo ""
echo "服务状态（应有 PID）："
launchctl list | grep stockpicker | awk '{printf "  %-45s PID=%s\n", $3, $1}' || echo "  请稍候 30 秒后再查看"
echo ""
echo "日志查看："
echo "  tail -f $STOCK_DIR/logs/feishu.log   # 飞书实时连接"
echo "  tail -f $STOCK_DIR/logs/daily.log    # 每日日报"
echo "  tail -f $STOCK_DIR/logs/monitor.log  # 盘中监控"
echo ""
echo "手动触发日报（测试）："
echo "  python3 $STOCK_DIR/run_daily.py --dry-run"
echo ""
echo "停止所有服务："
echo "  bash $STOCK_DIR/uninstall_mac.sh"
