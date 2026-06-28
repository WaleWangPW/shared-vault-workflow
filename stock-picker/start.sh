#!/usr/bin/env bash
# 启动脚本：在 Mac Mini 上手动启动日报 + 盘中监控。
# 正式部署请用 cron（见下方注释）。
#
# 用法：
#   ./start.sh             # 启动两个后台进程
#   ./start.sh --dry-run   # 仅打印日报，不推送
#
# Cron 示例（crontab -e）:
#   # 盘前 8:30 跑日报
#   30 8 * * 1-5 cd /path/to/stock-picker && python3 run_daily.py >> logs/daily.log 2>&1
#   # 9:20 启动盘中监控（它自己等到 9:30 开盘）
#   20 9 * * 1-5 cd /path/to/stock-picker && python3 realtime_monitor.py >> logs/monitor.log 2>&1
#   # 15:05 停止监控
#   5 15 * * 1-5 pkill -f realtime_monitor.py

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 从 .env 文件加载（若存在）
if [ -f .env ]; then
    # shellcheck disable=SC1091
    set -o allexport; source .env; set +o allexport
fi

# 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "python3 未找到，请先安装"
    exit 1
fi

mkdir -p logs

if [ "$1" = "--dry-run" ]; then
    echo "[start.sh] --dry-run 模式：运行日报但不推送"
    python3 run_daily.py --dry-run
    exit 0
fi

# 启动日报（立即跑一次）
python3 run_daily.py &
DAILY_PID=$!
echo "[start.sh] run_daily PID=$DAILY_PID"

# 启动盘中监控（后台常驻）
python3 realtime_monitor.py >> logs/monitor.log 2>&1 &
MONITOR_PID=$!
echo "[start.sh] realtime_monitor PID=$MONITOR_PID"
echo "[start.sh] 日志: logs/monitor.log"
echo "[start.sh] 停止监控: kill $MONITOR_PID"

wait $DAILY_PID
echo "[start.sh] 日报完成"
