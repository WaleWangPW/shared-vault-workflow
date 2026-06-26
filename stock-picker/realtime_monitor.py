#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时盘中监控（第五层）。
每 5 分钟取行情，检查：买点触及 ±2% / 止损触发 / 接近目标价 / 持仓异动。
同一信号当天只推送一次（去重），避免反复骚扰。

用法:
    python3 realtime_monitor.py              # 持续轮询（自动限交易时段 09:30–15:00）
    python3 realtime_monitor.py --once       # 只跑一轮（测试用）
    python3 realtime_monitor.py --interval 60  # 自定义轮询间隔（秒）
    python3 realtime_monitor.py --no-hours   # 忽略交易时段限制（调试用）

仅供研究学习，不构成投资建议。
"""
from __future__ import annotations
import sys
import time
import datetime as dt
from typing import Dict, List, Optional, Set
from config import WATCHLIST, HOLDINGS, MARKET_DEPTH, BUY_POINT
from data_source import get_source
from buy_point import calculate_buy_point
from push import send_feishu

DEFAULT_INTERVAL = 300       # 5 分钟
VOLUME_SPIKE_RATIO = 2.0     # 成交量放大阈值
MARKET_OPEN  = dt.time(9, 30)
MARKET_CLOSE = dt.time(15, 0)

# 今日已推送信号集（key = "code:signal_type:date"），进程重启后清零
_alerted: Set[str] = set()


def _alert_key(code: str, signal: str) -> str:
    return f"{code}:{signal}:{dt.date.today()}"


def _already_sent(code: str, signal: str) -> bool:
    return _alert_key(code, signal) in _alerted


def _mark_sent(code: str, signal: str):
    _alerted.add(_alert_key(code, signal))


def is_trading_hours() -> bool:
    now = dt.datetime.now()
    return now.weekday() < 5 and MARKET_OPEN <= now.time() <= MARKET_CLOSE


def check_watchlist_alerts(src) -> List[str]:
    alerts: List[str] = []
    for item in WATCHLIST:
        if item["market"] == "PRIMARY" or not item["code"]:
            continue
        code, market, name = item["code"], item["market"], item["name"]
        try:
            prices = src.get_daily(code, market, 130)
            q = src.get_quote(code, market)
            if not prices or q is None or q.price <= 0:
                continue

            current = q.price
            bp_result = calculate_buy_point(prices)
            buy_pt = bp_result.get("buy_point")
            stop_loss = bp_result.get("stop_loss")
            target = bp_result.get("target_price")

            # 买点触及 ±2%
            if buy_pt and not _already_sent(code, "near_buy"):
                if abs(current - buy_pt) / buy_pt <= 0.02:
                    alerts.append(
                        f"📍 {name}({code}) 触及买点区间 ¥{buy_pt:.2f}±2%"
                        f"（现价 ¥{current:.2f}）"
                    )
                    _mark_sent(code, "near_buy")

            # 跌破止损
            if stop_loss and current <= stop_loss and not _already_sent(code, "stop_loss"):
                alerts.append(
                    f"🔴 {name}({code}) 跌破止损位 ¥{stop_loss:.2f}"
                    f"（现价 ¥{current:.2f}）"
                )
                _mark_sent(code, "stop_loss")

            # 接近目标价（98%）
            if target and current >= target * 0.98 and not _already_sent(code, "near_target"):
                alerts.append(
                    f"🎯 {name}({code}) 接近目标价 ¥{target:.2f}"
                    f"（现价 ¥{current:.2f}）"
                )
                _mark_sent(code, "near_target")

        except Exception as e:
            pass  # 单只出错不阻断整体

    return alerts


def check_holding_alerts(src) -> List[str]:
    """对 config.HOLDINGS 中的持仓做止损检查。"""
    alerts: List[str] = []
    stop_threshold = BUY_POINT["stop_loss_ratio"] - 1.0   # e.g. 0.85 - 1 = -0.15

    for code, pos in HOLDINGS.items():
        cost = pos.get("cost", 0)
        if not cost:
            continue
        # 在 WATCHLIST 里找市场信息
        market = next(
            (item["market"] for item in WATCHLIST if item["code"] == code),
            "A"
        )
        name = next(
            (item["name"] for item in WATCHLIST if item["code"] == code),
            code
        )
        try:
            q = src.get_quote(code, market)
            if q is None or q.price <= 0:
                continue
            pnl_pct = (q.price - cost) / cost
            if pnl_pct <= stop_threshold and not _already_sent(code, "holding_stop"):
                alerts.append(
                    f"⚠️ 持仓 {name}({code}) 触及止损"
                    f"（成本 ¥{cost}，现价 ¥{q.price:.2f}，{pnl_pct*100:+.1f}%）"
                )
                _mark_sent(code, "holding_stop")
        except Exception:
            pass

    return alerts


def run_monitor(once: bool = False, interval: int = DEFAULT_INTERVAL,
                ignore_hours: bool = False):
    src = get_source()
    print(f"[monitor] 数据源: {src.name}  轮询间隔: {interval}s")
    print("[monitor] 按 Ctrl+C 停止")

    while True:
        if not ignore_hours and not is_trading_hours():
            if once:
                print("[monitor] 非交易时段，退出（--once 模式）")
                break
            print(f"[monitor] {dt.datetime.now().strftime('%H:%M')} 非交易时段，等待...")
            time.sleep(60)
            continue

        ts = dt.datetime.now().strftime("%H:%M")
        all_alerts: List[str] = []
        all_alerts.extend(check_watchlist_alerts(src))
        all_alerts.extend(check_holding_alerts(src))

        if all_alerts:
            msg = (
                f"🔔 实时监控 - {ts}\n\n"
                + "\n".join(all_alerts)
                + "\n\n⚠️ 仅供研究学习，不构成投资建议。"
            )
            print(msg)
            result = send_feishu(msg)
            print(f"[monitor] 推送: {result}")
        else:
            print(f"[monitor] {ts} 无异动")

        if once:
            break
        time.sleep(interval)


if __name__ == "__main__":
    _once         = "--once" in sys.argv
    _ignore_hours = "--no-hours" in sys.argv
    _interval     = DEFAULT_INTERVAL
    if "--interval" in sys.argv:
        idx = sys.argv.index("--interval")
        if idx + 1 < len(sys.argv):
            _interval = int(sys.argv[idx + 1])
    run_monitor(once=_once, interval=_interval, ignore_hours=_ignore_hours)
