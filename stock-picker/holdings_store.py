# -*- coding: utf-8 -*-
"""
持仓与动态关注列表的读写工具。

文件说明
--------
holdings.json
    格式: {"代码": {"name": "名称", "cost": 260.0, "shares": 100}}
    通过飞书指令「买入/卖出」写入，run_daily / realtime_monitor 读取。

dynamic_watchlist.json
    格式: [{"name": "名称", "code": "600036", "market": "A", "note": "..."}]
    通过飞书指令「加股/减股」写入，与 config.WATCHLIST 合并使用。

两个文件均为 JSON，写操作加文件锁，支持多进程并发。
"""
from __future__ import annotations
import json, os, threading
from typing import Dict, Any, List, Optional

_DIR = os.path.dirname(os.path.abspath(__file__))
HOLDINGS_PATH         = os.path.join(_DIR, "holdings.json")
DYNAMIC_WATCHLIST_PATH = os.path.join(_DIR, "dynamic_watchlist.json")

_h_lock  = threading.RLock()   # RLock 支持同线程重入（避免 add_holding → load_holdings 死锁）
_wl_lock = threading.RLock()


# ─────────────────────────── 持仓 ───────────────────────────

def load_holdings() -> Dict[str, Any]:
    """返回 {代码: {name, cost, shares}} 字典；文件不存在返回 {}。"""
    with _h_lock:
        if not os.path.exists(HOLDINGS_PATH):
            return {}
        try:
            with open(HOLDINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}


def _save_holdings(data: Dict[str, Any]):
    with open(HOLDINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_holding(code: str, name: str, cost: float, shares: int) -> str:
    """买入：写入/更新持仓，返回确认文字。"""
    with _h_lock:
        data = load_holdings()
        data[code] = {"name": name, "cost": cost, "shares": shares}
        _save_holdings(data)
    return f"✅ 已记录持仓：{name}({code})  成本 ¥{cost}  {shares}股"


def remove_holding(code: str) -> str:
    """卖出：删除持仓，返回确认文字；不存在则提示。"""
    with _h_lock:
        data = load_holdings()
        if code not in data:
            return f"⚠️ {code} 不在持仓中"
        name = data[code].get("name", code)
        del data[code]
        _save_holdings(data)
    return f"✅ 已清除持仓：{name}({code})"


# ─────────────────────────── 动态关注列表 ───────────────────────────

def load_dynamic_watchlist() -> List[Dict]:
    """返回动态追加的关注股列表；文件不存在返回 []。"""
    with _wl_lock:
        if not os.path.exists(DYNAMIC_WATCHLIST_PATH):
            return []
        try:
            with open(DYNAMIC_WATCHLIST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []


def _save_dynamic_watchlist(data: List[Dict]):
    with open(DYNAMIC_WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_to_watchlist(code: str, name: str, market: str = "A",
                     note: str = "飞书加入") -> str:
    """加股：追加到动态列表，代码重复则更新名称/市场，返回确认文字。"""
    with _wl_lock:
        data = load_dynamic_watchlist()
        for item in data:
            if item["code"] == code:
                item.update({"name": name, "market": market, "note": note})
                _save_dynamic_watchlist(data)
                return f"✅ 已更新关注：{name}({code}) [{market}]"
        data.append({"name": name, "code": code, "market": market, "note": note})
        _save_dynamic_watchlist(data)
    return f"✅ 已加入关注：{name}({code}) [{market}]"


def remove_from_watchlist(code: str) -> str:
    """减股：从动态列表删除，config.WATCHLIST 中的不受影响，返回确认文字。"""
    with _wl_lock:
        data = load_dynamic_watchlist()
        before = len(data)
        data = [x for x in data if x["code"] != code]
        if len(data) == before:
            return f"⚠️ {code} 不在动态关注列表中（config 基础列表不可通过此指令删除）"
        _save_dynamic_watchlist(data)
    return f"✅ 已从关注列表删除：{code}"


# ─────────────────────────── 合并工具 ───────────────────────────

def effective_watchlist(base_watchlist: List[Dict]) -> List[Dict]:
    """
    返回 config.WATCHLIST + dynamic_watchlist.json 的合并列表。
    动态列表中与 base 代码重复的项被忽略（base 优先）。
    """
    base_codes = {item["code"] for item in base_watchlist if item.get("code")}
    extra = [x for x in load_dynamic_watchlist() if x.get("code") not in base_codes]
    return base_watchlist + extra
