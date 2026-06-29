#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票指令 CLI —— 供 openclaw 调用。

用法：
  python3 cmd.py 买入 688008 260.0 100
  python3 cmd.py 卖出 688008
  python3 cmd.py 持仓
  python3 cmd.py 加股 600036 招商银行 A
  python3 cmd.py 减股 600036
  python3 cmd.py 关注列表
  python3 cmd.py 查 688008
  python3 cmd.py 日报

输出结果打印到 stdout，供 openclaw 读取后回复用户。
仅供研究学习，不构成投资建议。
"""
from __future__ import annotations
import sys, os

# 确保 stock-picker 目录在 path 里（无论从哪里调用）
_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from holdings_store import (
    load_holdings, add_holding, remove_holding,
    add_to_watchlist, remove_from_watchlist,
    load_dynamic_watchlist, effective_watchlist,
)
from config import WATCHLIST


def cmd_mairu(args):
    """买入 <代码> <成本价> <股数>"""
    if len(args) < 3:
        return "格式：买入 <代码> <成本价> <股数>\n例：买入 688008 260.0 100"
    code = args[0]
    try:
        cost   = float(args[1])
        shares = int(args[2])
    except ValueError:
        return "成本价/股数格式错误，请输入数字"
    wl_item = next((w for w in WATCHLIST if w["code"] == code), None)
    name = wl_item["name"] if wl_item else code
    return add_holding(code, name, cost, shares)


def cmd_mairu_with_name(args):
    """买入 <代码> <名称> <成本价> <股数>（名称可选）"""
    if len(args) < 3:
        return "格式：买入 <代码> <成本价> <股数>"
    # 兼容带名称和不带名称两种格式
    code = args[0]
    if len(args) >= 4:
        try:
            float(args[1])
            # args[1] 是数字 → 格式是「代码 成本价 股数」
            cost   = float(args[1])
            shares = int(args[2])
            name   = next((w["name"] for w in WATCHLIST if w["code"] == code), code)
        except ValueError:
            # args[1] 是名称 → 格式是「代码 名称 成本价 股数」
            name   = args[1]
            cost   = float(args[2])
            shares = int(args[3]) if len(args) >= 4 else 0
    else:
        try:
            cost   = float(args[1])
            shares = int(args[2])
            name   = next((w["name"] for w in WATCHLIST if w["code"] == code), code)
        except (ValueError, IndexError):
            return "格式错误"
    return add_holding(code, name, cost, shares)


def cmd_chicangs():
    """持仓 — 列出全部持仓和盈亏"""
    import datetime as dt
    holdings = load_holdings()
    if not holdings:
        return "📭 当前无持仓记录"

    try:
        from data_source import get_source
        src = get_source()
    except Exception:
        src = None

    lines = [f"📈 持仓列表（{dt.date.today()}）\n"]
    total_cost = total_val = 0.0
    for code, pos in holdings.items():
        name  = pos.get("name", code)
        cost  = pos.get("cost") or 0.0
        shs   = pos.get("shares") or 0
        price_str = pnl_str = "N/A"
        try:
            if src:
                wl_item = next((w for w in WATCHLIST if w["code"] == code), {})
                market  = wl_item.get("market", "A")
                q = src.get_quote(code, market)
                if q and q.price:
                    price_str = f"¥{q.price:.2f}"
                    pnl = (q.price - cost) / cost * 100 if cost else 0
                    pnl_str = f"{pnl:+.1f}%"
                    total_cost += cost * shs
                    total_val  += q.price * shs
        except Exception:
            pass
        lines.append(f"  {name}({code})\n  成本 ¥{cost}  现价 {price_str}  {shs}股  盈亏 {pnl_str}")

    if total_cost > 0:
        total_pnl = (total_val - total_cost) / total_cost * 100
        lines.append(f"\n汇总盈亏：{total_pnl:+.1f}%")
    lines.append("\n⚠️ 仅供研究，非投资建议")
    return "\n".join(lines)


def cmd_cha(args):
    """查 <代码> — 当前价/买点/止损"""
    if not args:
        return "格式：查 <代码>\n例：查 688008"
    code = args[0]
    from data_source import get_source
    from buy_point import calculate_buy_point
    import datetime as dt

    wl = effective_watchlist(WATCHLIST)
    wl_item = next((w for w in wl if w["code"] == code), {})
    market = wl_item.get("market", "A")
    name   = wl_item.get("name", code)
    try:
        src    = get_source()
        prices = src.get_daily(code, market, 130)
        q      = src.get_quote(code, market)
        if not prices or q is None:
            return f"⚠️ {code} 无行情数据"
        bp = calculate_buy_point(prices)
        lines = [
            f"📊 {name}({code}) [{market}]  {dt.date.today()}",
            f"  现价：¥{q.price:.3f}",
            f"  买点：¥{bp.get('buy_point', 'N/A')}",
            f"  止损：¥{bp.get('stop_loss', 'N/A')}",
            f"  目标：{'¥'+str(bp.get('target_price')) if bp.get('target_price') else 'N/A'}",
            f"  MA20：¥{bp.get('ma20', 'N/A')}",
            f"  趋势：{'↑ 上升' if bp.get('trend_up') else '↓ 下降' if bp.get('trend_up') is False else 'N/A'}",
            f"\n⚠️ 仅供研究，非投资建议",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"⚠️ 查询失败：{e}"


def cmd_ribao():
    """日报 — 立即触发完整选股日报并推送飞书"""
    try:
        import run_daily
        run_daily.run(dry_run=False)
        return "✅ 日报已触发，请查看飞书推送"
    except Exception as e:
        return f"⚠️ 日报触发失败：{e}"


def cmd_guanzhu_list():
    """关注列表"""
    base = [w for w in WATCHLIST if w.get("code")]
    dyn  = load_dynamic_watchlist()
    lines = [f"👁 关注列表（共 {len(base)+len(dyn)} 只）\n"]
    lines.append("【基础列表】")
    for w in base:
        lines.append(f"  {w['name']}({w['code']}) [{w['market']}]  {w.get('note','')}")
    if dyn:
        lines.append("\n【飞书动态加入】")
        for w in dyn:
            lines.append(f"  {w['name']}({w['code']}) [{w['market']}]  {w.get('note','')}")
    return "\n".join(lines)


HELP = """📋 股票助手指令

  买入 <代码> <成本价> <股数>       买入 688008 260.0 100
  卖出 <代码>                       卖出 688008
  持仓                              列出所有持仓和盈亏
  加股 <代码> <名称> [市场]         加股 600036 招商银行 A
  减股 <代码>                       减股 688008
  关注列表                          查看全部关注股
  查 <代码>                         查 688008
  日报                              立即触发选股日报

⚠️ 仅供研究学习，不构成投资建议"""


def main():
    args = sys.argv[1:]
    if not args:
        print(HELP)
        return

    cmd  = args[0]
    rest = args[1:]

    if cmd == "买入":
        print(cmd_mairu_with_name(rest))
    elif cmd == "卖出":
        if not rest:
            print("格式：卖出 <代码>")
        else:
            print(remove_holding(rest[0]))
    elif cmd == "持仓":
        print(cmd_chicangs())
    elif cmd == "加股":
        if len(rest) < 2:
            print("格式：加股 <代码> <名称> [市场A/HK/US]")
        else:
            market = rest[2].upper() if len(rest) >= 3 else "A"
            print(add_to_watchlist(rest[0], rest[1], market))
    elif cmd == "减股":
        if not rest:
            print("格式：减股 <代码>")
        else:
            print(remove_from_watchlist(rest[0]))
    elif cmd == "关注列表":
        print(cmd_guanzhu_list())
    elif cmd == "查":
        print(cmd_cha(rest))
    elif cmd == "日报":
        print(cmd_ribao())
    elif cmd in ("帮助", "help"):
        print(HELP)
    else:
        print(f"未知指令：{cmd}\n\n{HELP}")


if __name__ == "__main__":
    main()
