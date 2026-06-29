#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票指令 CLI —— 供 openclaw 调用。

用法：
  python3 cmd.py 买入 688008 260.0 100
  python3 cmd.py 买入 HK6809 405.7 300    # 自动转为 06809
  python3 cmd.py 卖出 688008
  python3 cmd.py 持仓
  python3 cmd.py 分析                      # 全仓+关注列表综合分析
  python3 cmd.py 加股 600036 招商银行 A
  python3 cmd.py 减股 600036
  python3 cmd.py 关注列表
  python3 cmd.py 查 688008
  python3 cmd.py 日报

输出纯文本，供 openclaw 读取后回复用户。
仅供研究学习，不构成投资建议。
"""
from __future__ import annotations
import sys, os, datetime as dt
from typing import Optional, Dict, List

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)


def _load_dotenv():
    """从脚本同目录的 .env 自动加载环境变量（支持有/无 export 前缀）。
    已存在于 os.environ 的变量不覆盖，确保 shell 层面 export 的优先级更高。
    """
    env_path = os.path.join(_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv()

from holdings_store import (
    load_holdings, add_holding, remove_holding,
    add_to_watchlist, remove_from_watchlist,
    load_dynamic_watchlist, effective_watchlist,
)
from config import WATCHLIST


# ── 代码标准化 ─────────────────────────────────────────────────────────────────

def _norm(code: str) -> str:
    """HK6082 → 06082；其他不变。"""
    c = code.strip()
    if c.upper().startswith("HK") and c[2:].isdigit():
        return c[2:].zfill(5)
    return c


# ── 持仓 ──────────────────────────────────────────────────────────────────────

def cmd_mairu(args):
    if len(args) < 3:
        return "格式：买入 <代码> <成本价> <股数>\n例：买入 688008 260.0 100"
    code = _norm(args[0])
    # 兼容「代码 成本价 股数」和「代码 名称 成本价 股数」
    try:
        cost_idx = 1
        float(args[1])   # 如果 args[1] 能转 float 则没有名称
    except ValueError:
        cost_idx = 2      # args[1] 是名称

    try:
        name   = args[1] if cost_idx == 2 else None
        cost   = float(args[cost_idx])
        shares = int(args[cost_idx + 1])
    except (ValueError, IndexError):
        return "格式错误，请检查成本价和股数"

    wl = effective_watchlist(WATCHLIST)
    if name is None:
        name = next((w["name"] for w in wl if w["code"] == code), code)
    return add_holding(code, name, cost, shares)


def cmd_chicangs():
    holdings = load_holdings()
    if not holdings:
        return "📭 当前无持仓记录"

    src = _get_src()
    wl  = effective_watchlist(WATCHLIST)
    lines = [f"📈 持仓列表（{dt.date.today()}）\n"]
    total_cost = total_val = 0.0

    for code, pos in holdings.items():
        name  = pos.get("name", code)
        cost  = pos.get("cost") or 0.0
        shs   = pos.get("shares") or 0
        price_str = pnl_str = "N/A"
        try:
            if src:
                market = next((w["market"] for w in wl if w["code"] == code), "A")
                q = src.get_quote(code, market)
                if q and q.price:
                    cur = q.price
                    price_str = f"¥{cur:.3f}"
                    if cost:
                        pnl = (cur - cost) / cost * 100
                        pnl_str = f"{pnl:+.1f}%"
                        total_cost += cost * shs
                        total_val  += cur * shs
        except Exception:
            pass
        lines.append(f"  {name}({code})\n  成本¥{cost}  现价{price_str}  {shs}股  盈亏{pnl_str}")

    if total_cost > 0:
        lines.append(f"\n汇总盈亏：{(total_val-total_cost)/total_cost*100:+.1f}%")
    lines.append("\n⚠️ 仅供研究，非投资建议")
    return "\n".join(lines)


# ── 综合分析 ───────────────────────────────────────────────────────────────────

def cmd_fenxi():
    """全仓 + 关注列表综合分析，含买点状态和推荐。"""
    from buy_point import calculate_buy_point
    from screener import score_stock, passes_basic
    from data_source import get_source, Financials

    src      = _get_src()
    wl       = effective_watchlist(WATCHLIST)
    holdings = load_holdings()
    today    = dt.date.today().strftime("%Y-%m-%d")
    now_t    = dt.datetime.now().strftime("%H:%M")

    lines = [f"📊 全仓分析报告  {today} {now_t}", ""]

    # ── 持仓分析 ──────────────────────────────────────────────────────────────
    if holdings:
        lines.append("━━ 持仓 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        total_cost = total_val = 0.0

        for code, pos in holdings.items():
            name   = pos.get("name", code)
            cost   = pos.get("cost") or 0.0
            shs    = pos.get("shares") or 0
            market = next((w["market"] for w in wl if w["code"] == code), "A")

            q = bp = None
            f_data = None
            prices = []
            try:
                if src:
                    prices = src.get_daily(code, market, 130)
                    q = src.get_quote(code, market)
                    if prices:
                        bp = calculate_buy_point(prices)
                    if market == "A":
                        f_data = src.get_financials(code, market)
            except Exception:
                pass

            cur       = q.price if q and q.price else None
            pct       = q.pct_change if q else None
            pnl_pct   = (cur - cost) / cost * 100 if cur and cost else None
            mkt_val   = cur * shs if cur else None

            pe_str    = f"  PE={q.pe_ttm:.1f}" if q and q.pe_ttm else ""
            pct_str   = f"  今日{pct:+.2f}%" if pct is not None else ""
            price_str = f"¥{cur:.3f}" if cur else "N/A"
            pnl_str   = f"{pnl_pct:+.1f}%" if pnl_pct is not None else "N/A"
            val_str   = f"¥{mkt_val:,.0f}" if mkt_val else "N/A"

            if cur and cost:
                total_cost += cost * shs
                total_val  += cur * shs

            lines.append(f"\n{name}({code}/{market})  {price_str}{pct_str}{pe_str}")
            lines.append(f"  成本¥{cost} × {shs}股  盈亏{pnl_str}  市值{val_str}")

            # 基本面（A股 Tushare 模式下有数据）
            if f_data:
                fparts = []
                if f_data.revenue_growth_yoy is not None:
                    fparts.append(f"营收增速{f_data.revenue_growth_yoy*100:+.0f}%")
                if f_data.profit_growth_yoy is not None:
                    fparts.append(f"利润增速{f_data.profit_growth_yoy*100:+.0f}%")
                if f_data.operating_cashflow is not None:
                    cf = f_data.operating_cashflow / 1e8
                    fparts.append(f"经营现金流{cf:+.1f}亿")
                if fparts:
                    lines.append(f"  基本面: {' | '.join(fparts)}")

            if bp and not bp.get("error"):
                buy_pt   = bp.get("buy_point")
                stop     = bp.get("stop_loss")
                target   = bp.get("target_price")
                trend    = bp.get("trend_up")
                trend_s  = "↑上升趋势" if trend else ("↓下降趋势" if trend is False else "趋势未知")

                signals = []
                if cur and buy_pt:
                    diff = (cur - buy_pt) / buy_pt
                    if abs(diff) <= 0.03:
                        signals.append(f"📍接近买点(¥{buy_pt:.2f} ±3%)")
                    elif diff < -0.03:
                        signals.append(f"低于买点 {abs(diff)*100:.1f}%")
                if cur and stop and cur <= stop:
                    signals.append(f"🔴已跌破止损(¥{stop:.2f})")
                elif cur and stop:
                    dist = (cur - stop) / stop * 100
                    if dist < 10:
                        signals.append(f"⚠️距止损仅{dist:.1f}%")
                if cur and target and cur >= target * 0.95:
                    signals.append(f"🎯接近目标价(¥{target:.2f})")

                buy_s = f"买点¥{buy_pt:.2f}" if buy_pt else ""
                stp_s = f"止损¥{stop:.2f}" if stop else ""
                tgt_s = f"目标¥{target:.2f}" if target else ""
                ref_parts = [s for s in [buy_s, stp_s, tgt_s] if s]
                lines.append(f"  {trend_s}  {' | '.join(ref_parts)}")
                if signals:
                    lines.append(f"  信号: {' | '.join(signals)}")
            else:
                err_msg = bp.get("error", "数据不足") if bp else "数据不足"
                lines.append(f"  {err_msg}")

        if total_cost > 0:
            lines.append(f"\n持仓总盈亏: {(total_val-total_cost)/total_cost*100:+.1f}%  总市值¥{total_val:,.0f}")

    # ── 关注列表（未持仓）分析 ─────────────────────────────────────────────────
    held_codes = set(holdings.keys())
    watch_only = [w for w in wl if w.get("code") and w["market"] != "PRIMARY"
                  and w["code"] not in held_codes]

    if watch_only:
        lines.append("\n━━ 关注（未持仓）━━━━━━━━━━━━━━━━━━━━━━━━━━")
        candidates = []

        for item in watch_only:
            code, market, name = item["code"], item["market"], item["name"]
            q = bp = None
            prices = []
            try:
                if src:
                    prices = src.get_daily(code, market, 252)
                    q = src.get_quote(code, market)
                    if prices:
                        bp = calculate_buy_point(prices[-120:])
            except Exception:
                pass

            cur     = q.price if q and q.price else None
            pct     = q.pct_change if q else None
            pct_str = f"  今日{pct:+.2f}%" if pct is not None else ""
            p_str   = f"¥{cur:.3f}" if cur else "N/A"

            # 简单打分（仅行情，无财务）
            score = 0
            signals = []
            if bp and not bp.get("error") and cur:
                buy_pt = bp.get("buy_point")
                stop   = bp.get("stop_loss")
                trend  = bp.get("trend_up")
                if trend:
                    score += 10
                    signals.append("↑趋势")
                if buy_pt and abs(cur - buy_pt) / buy_pt <= 0.05:
                    score += 20
                    signals.append("📍近买点")
                if stop and cur <= stop:
                    score -= 30
                    signals.append("🔴破止损")
                if pct is not None and pct < -3:
                    score -= 5
                    signals.append(f"大跌{pct:.1f}%")
                if pct is not None and pct > 5:
                    score += 5
                    signals.append(f"强势+{pct:.1f}%")

            candidates.append({
                "name": name, "code": code, "market": market,
                "price": cur, "pct_str": pct_str, "p_str": p_str,
                "bp": bp, "score": score, "signals": signals,
            })

        # 按得分排序
        candidates.sort(key=lambda x: x["score"], reverse=True)

        for c in candidates:
            lines.append(f"\n{c['name']}({c['code']}/{c['market']})  {c['p_str']}{c['pct_str']}")
            bp = c["bp"]
            if bp and not bp.get("error"):
                buy_pt = bp.get("buy_point")
                stop   = bp.get("stop_loss")
                trend  = "↑" if bp.get("trend_up") else ("↓" if bp.get("trend_up") is False else "—")
                refs   = []
                if buy_pt: refs.append(f"买点¥{buy_pt:.2f}")
                if stop:   refs.append(f"止损¥{stop:.2f}")
                lines.append(f"  趋势{trend}  {' | '.join(refs)}")
            if c["signals"]:
                lines.append(f"  信号: {' | '.join(c['signals'])}")

        # 推荐 top2
        top = [c for c in candidates if c["score"] > 0][:2]
        if top:
            lines.append("\n━━ 今日可关注 ━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            for c in top:
                lines.append(f"  ⭐ {c['name']}({c['code']})  得分{c['score']}  {' '.join(c['signals'])}")

    lines.append("\n⚠️ 仅供研究学习，不构成投资建议")
    return "\n".join(lines)


# ── 查单股 ─────────────────────────────────────────────────────────────────────

def cmd_cha(args):
    if not args:
        return "格式：查 <代码>\n例：查 688008"
    from buy_point import calculate_buy_point
    code = _norm(args[0])
    wl   = effective_watchlist(WATCHLIST)
    item = next((w for w in wl if w["code"] == code), {})
    market = item.get("market", "A")
    name   = item.get("name", code)
    src    = _get_src()
    try:
        prices = src.get_daily(code, market, 130)
        q      = src.get_quote(code, market)
        if not prices or q is None:
            return f"⚠️ {code} 无行情数据"
        bp = calculate_buy_point(prices)
        pct_s = f"  今日{q.pct_change:+.2f}%" if q.pct_change else ""
        lines = [
            f"📊 {name}({code}/{market})  {dt.date.today()}",
            f"  现价：¥{q.price:.3f}{pct_s}",
            f"  买点：¥{bp.get('buy_point', 'N/A')}",
            f"  止损：¥{bp.get('stop_loss', 'N/A')}",
            f"  目标：{'¥'+str(bp.get('target_price')) if bp.get('target_price') else 'N/A'}",
            f"  MA20：¥{bp.get('ma20', 'N/A')}",
            f"  趋势：{'↑ 上升' if bp.get('trend_up') else '↓ 下降' if bp.get('trend_up') is False else 'N/A'}",
            "\n⚠️ 仅供研究，非投资建议",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"⚠️ 查询失败：{e}"


# ── 日报 ───────────────────────────────────────────────────────────────────────

def cmd_ribao():
    try:
        import run_daily
        run_daily.run(dry_run=False)
        return "✅ 日报已触发，请查看飞书推送"
    except Exception as e:
        return f"⚠️ 日报触发失败：{e}"


# ── 关注列表 ───────────────────────────────────────────────────────────────────

def cmd_guanzhu_list():
    base = [w for w in WATCHLIST if w.get("code")]
    dyn  = load_dynamic_watchlist()
    lines = [f"👁 关注列表（共 {len(base)+len(dyn)} 只）\n"]
    lines.append("【基础列表】")
    for w in base:
        lines.append(f"  {w['name']}({w['code']}) [{w['market']}]  {w.get('note','')}")
    if dyn:
        lines.append("\n【动态加入】")
        for w in dyn:
            lines.append(f"  {w['name']}({w['code']}) [{w['market']}]  {w.get('note','')}")
    return "\n".join(lines)


# ── 选股 ───────────────────────────────────────────────────────────────────────

def cmd_xuangu(args):
    """全市场选股扫描，支持可选行业关键词。"""
    from market_screener import run_market_screen
    sector_kw = args[0] if args else ""
    top_n = 10
    deep_n = 40
    for i, a in enumerate(args):
        if a in ("-n", "--top") and i + 1 < len(args):
            try:
                top_n = int(args[i + 1])
            except ValueError:
                pass
    return run_market_screen(sector_kw=sector_kw, top_n=top_n, deep_n=deep_n)


# ── 诊断 ───────────────────────────────────────────────────────────────────────

def cmd_zhenduan():
    """快速验证各市场行情，并显示数据源和凭证配置状态。"""
    import os
    lines = [f"🔧 数据源诊断  {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}"]

    src = _get_src()
    if src is None:
        return "❌ 数据源初始化失败，请检查依赖包"
    lines.append(f"数据源: {src.name}")

    # 快速测试各市场（用持仓/关注列表里的真实代码）
    wl = effective_watchlist(WATCHLIST)
    holdings = load_holdings()
    test_cases: list = []
    for market in ("A", "HK", "US"):
        c = next((w for w in wl if w.get("market") == market and w.get("code")), None)
        if c:
            test_cases.append((c["name"], c["code"], market))

    lines.append("")
    for label, code, market in test_cases:
        try:
            q = src.get_quote(code, market)
            if q and q.price:
                pe_part = f"  PE={q.pe_ttm:.1f}" if q.pe_ttm else ""
                lines.append(f"✅ {market} {label}({code}): ¥{q.price:.3f}  {q.pct_change:+.2f}%{pe_part}")
            else:
                lines.append(f"⚠️ {market} {label}({code}): 无行情（非交易日/网络）")
        except Exception as e:
            lines.append(f"❌ {market} {label}({code}): {str(e)[:80]}")

    lines.append("")
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    lines.append(f"Tushare: {'✅ 已配置（A股财报+PE历史分位）' if token else '⚠️ 未配置（无A股财报，仅技术面）'}")
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    lines.append(f"飞书推送: {'✅ 已配置' if app_id else '⚠️ 未配置'}")
    return "\n".join(lines)


# ── 工具 ───────────────────────────────────────────────────────────────────────

def _get_src():
    try:
        from data_source import get_source
        return get_source()
    except Exception:
        return None


HELP = """📋 股票助手指令

  买入 <代码> <成本价> <股数>       买入 688008 260.0 100
  卖出 <代码>                       卖出 688008
  持仓                              列出所有持仓和盈亏
  分析                              全仓+关注列表综合分析+推荐
  加股 <代码> <名称> [市场]         加股 600036 招商银行 A
  减股 <代码>                       减股 688008
  关注列表                          查看全部关注股
  查 <代码>                         查 688008
  日报                              立即触发选股日报
  选股 [行业关键词]                 全市场A股扫描，如：选股 半导体
  诊断                              验证数据源和凭证配置

HK代码支持 HK6082 或 06082 两种格式（自动转换）
⚠️ 仅供研究学习，不构成投资建议"""


def main():
    args = sys.argv[1:]
    if not args:
        print(HELP)
        return

    cmd  = args[0]
    rest = args[1:]

    dispatch = {
        "买入":   lambda: cmd_mairu(rest),
        "卖出":   lambda: remove_holding(_norm(rest[0])) if rest else "格式：卖出 <代码>",
        "持仓":   lambda: cmd_chicangs(),
        "分析":   lambda: cmd_fenxi(),
        "关注列表": lambda: cmd_guanzhu_list(),
        "关注":   lambda: cmd_guanzhu_list(),
        "加股":   lambda: (add_to_watchlist(_norm(rest[0]), rest[1],
                            rest[2].upper() if len(rest) >= 3 else "A")
                           if len(rest) >= 2 else "格式：加股 <代码> <名称> [市场]"),
        "减股":   lambda: remove_from_watchlist(_norm(rest[0])) if rest else "格式：减股 <代码>",
        "查":     lambda: cmd_cha(rest),
        "日报":   lambda: cmd_ribao(),
        "选股":   lambda: cmd_xuangu(rest),
        "诊断":   lambda: cmd_zhenduan(),
        "帮助":   lambda: HELP,
        "help":   lambda: HELP,
    }

    fn = dispatch.get(cmd)
    if fn:
        print(fn())
    else:
        print(f"未知指令：{cmd}\n\n{HELP}")


if __name__ == "__main__":
    main()
