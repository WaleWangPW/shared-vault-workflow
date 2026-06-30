#!/usr/bin/env bash
# 卸载 launchd 服务（停止所有自动任务）
set -euo pipefail

LAUNCH_DIR="$HOME/Library/LaunchAgents"

for label in com.stockpicker.feishu com.stockpicker.daily com.stockpicker.monitor; do
    plist="$LAUNCH_DIR/${label}.plist"
    if [ -f "$plist" ]; then
        launchctl unload "$plist" 2>/dev/null || true
        rm "$plist"
        echo "✅ 已移除 $label"
    fi
done

pkill -f feishu_handler.py 2>/dev/null && echo "✅ feishu_handler 进程已停止" || true
pkill -f realtime_monitor.py 2>/dev/null && echo "✅ realtime_monitor 进程已停止" || true

echo "卸载完成"
