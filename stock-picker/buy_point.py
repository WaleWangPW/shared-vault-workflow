# -*- coding: utf-8 -*-
"""
买点 / 风控计算 —— 纯函数，可离线单元测试。
公式来自 LOGIC.md「第五步：买点计算」。
仅供研究参考，非交易建议。
"""
from __future__ import annotations
from typing import List, Optional, Dict
from config import BUY_POINT


def sma(prices: List[float], n: int) -> Optional[float]:
    if len(prices) < n:
        return None
    return sum(prices[-n:]) / n


def trend_up(prices: List[float]) -> Optional[bool]:
    """MA_short > MA_long 视为上升趋势。"""
    s = sma(prices, BUY_POINT["ma_short"])
    l = sma(prices, BUY_POINT["ma_long"])
    if s is None or l is None:
        return None
    return s > l


def recent_support(prices: List[float], lookback: int = 60) -> Optional[float]:
    """以近 lookback 日最低收盘价作为简易支撑位。"""
    if not prices:
        return None
    return min(prices[-lookback:])


def calculate_buy_point(prices: List[float], eps_ttm: Optional[float] = None) -> Dict:
    """
    返回 买点/止损/目标价/风险收益比。
    买点 = max(MA20*0.98, 支撑位)；止损 = 买点*0.85；
    目标价 = eps_ttm * target_pe（无 eps 时为 None）。
    """
    ma20 = sma(prices, BUY_POINT["ma_short"])
    support = recent_support(prices)
    if ma20 is None or support is None:
        return {"error": "数据不足，需至少 %d 个交易日" % BUY_POINT["ma_long"]}

    buy = max(ma20 * BUY_POINT["buy_discount_to_ma20"], support)
    stop = buy * BUY_POINT["stop_loss_ratio"]
    target = eps_ttm * BUY_POINT["target_pe"] if eps_ttm else None

    rr = None
    if target and buy > stop:
        rr = round((target - buy) / (buy - stop), 2)

    return {
        "current": round(prices[-1], 3),
        "ma20": round(ma20, 3),
        "support": round(support, 3),
        "buy_point": round(buy, 3),
        "stop_loss": round(stop, 3),
        "target_price": round(target, 3) if target else None,
        "risk_reward": rr,
        "trend_up": trend_up(prices),
    }
