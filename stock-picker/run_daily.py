#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日选股编排入口（盘前 8:30 由 cron 调用）。

流程：取数据源 → 遍历关注列表 → 基础筛选 + 加分（含降权护栏）+ 买点 → 排序 → 推送。
未配置 TUSHARE_TOKEN 时自动 AKShare-only 模式（跳过财报条件）。

用法:
    python3 run_daily.py            # 正常运行
    python3 run_daily.py --dry-run  # 只打印，不推送

仅供研究学习，不构成投资建议。
"""
from __future__ import annotations
import sys, os
import datetime as dt


def _load_dotenv():
    d = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(d, ".env")
    if not os.path.exists(p):
        return
    with open(p, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


_load_dotenv()

from config import WATCHLIST, MAX_HOLDINGS, MARKET_DEPTH
from data_source import get_source
from screener import passes_basic, score_stock, rank
from buy_point import calculate_buy_point
from push import build_daily_text, send_feishu, send_feishu_card
from feishu_card import build_daily_card
from holdings_store import load_holdings, effective_watchlist


def run(dry_run: bool = False):
    src = get_source()
    print(f"[run_daily] 数据源: {src.name}")
    today = dt.date.today().strftime("%Y-%m-%d")

    watchlist = effective_watchlist(WATCHLIST)
    holdings  = load_holdings()

    candidates = []
    for item in watchlist:
        if item["market"] == "PRIMARY" or not item["code"]:
            continue
        code, market = item["code"], item["market"]
        try:
            # 取 252 日数据：用于一年涨幅计算（触发降权护栏）
            prices_long = src.get_daily(code, market, 252)
            q = src.get_quote(code, market)
            f = src.get_financials(code, market)
        except Exception as e:
            print(f"  [skip] {item['name']} {code}: {repr(e)[:120]}")
            continue
        if q is None or not prices_long:
            continue

        # 买点计算只用近 120 日
        prices = prices_long[-120:]

        # ── 计算降权护栏所需 flags ──────────────────────────────────────
        # 一年涨幅（用交易日序列长度估算，≥200 条视为足够）
        price_1y_pct: float | None = None
        if len(prices_long) >= 200:
            p0 = prices_long[0]
            if p0 and p0 > 0:
                price_1y_pct = (prices_long[-1] - p0) / p0

        # PE 历史分位（TushareSource 精确；AKShareSource 也会尝试）
        pe_percentile = src.get_pe_percentile(code, market)

        flags = {
            "pe_percentile": pe_percentile,
            "price_1y_pct": price_1y_pct,
        }

        # ── 筛选 + 评分 ─────────────────────────────────────────────────
        depth = MARKET_DEPTH.get(market, "lite")
        basic = passes_basic(q, f)

        if depth == "full":
            sc = score_stock(q, f, flags)
        else:
            # lite 市场（港股/美股）只做行情+技术面
            sc = {"score": 0, "hits": ["lite:仅技术面"]}

        bp = calculate_buy_point(prices, f.eps_ttm)

        candidates.append({
            "name": item["name"], "code": code, "market": market, "depth": depth,
            "score": sc["score"], "hits": sc["hits"],
            "basic_pass": basic["pass"], "skipped": basic["skipped"],
            "buy": bp,
            "today_pct": q.pct_change if q else None,
            "pe_ttm":    q.pe_ttm    if q else None,
        })

        # 控制台简报
        pct_str = f"{price_1y_pct*100:+.0f}%" if price_1y_pct is not None else "N/A"
        pe_str  = f"{pe_percentile*100:.0f}%分位" if pe_percentile is not None else "N/A"
        print(f"  {item['name']:10s} 得分={sc['score']:+3d}  1y={pct_str}  PE={pe_str}  {'✓' if basic['pass'] else '✗'}")

    top = rank(candidates, MAX_HOLDINGS)

    holdings_view = []
    for hcode, pos in holdings.items():
        cost = pos.get("cost")
        wl_item = next((w for w in watchlist if w["code"] == hcode), {})
        hmarket   = wl_item.get("market", "A")
        hname     = wl_item.get("name", hcode)
        hprice    = None
        pnl_pct   = None
        today_pct = None
        signal    = None
        buy_point = stop_loss = None
        try:
            hq = src.get_quote(hcode, hmarket)
            if hq and hq.price:
                hprice    = round(hq.price, 3)
                today_pct = hq.pct_change
                if cost:
                    pnl_pct = f"{(hq.price - cost) / cost * 100:+.1f}%"
            hprices = src.get_daily(hcode, hmarket, 130)
            if hprices:
                hbp = calculate_buy_point(hprices)
                if not hbp.get("error") and hprice:
                    buy_point = hbp.get("buy_point")
                    stop_loss = hbp.get("stop_loss")
                    target_p  = hbp.get("target_price")
                    sigs = []
                    if buy_point and abs(hprice - buy_point) / buy_point <= 0.03:
                        sigs.append("📍近买点")
                    if stop_loss and hprice <= stop_loss:
                        sigs.append("🔴破止损")
                    elif stop_loss and (hprice - stop_loss) / stop_loss < 0.08:
                        sigs.append(f"⚠️距止损{(hprice-stop_loss)/stop_loss*100:.1f}%")
                    if target_p and hprice >= target_p * 0.95:
                        sigs.append("🎯近目标")
                    if sigs:
                        signal = " | ".join(sigs)
        except Exception:
            pass
        holdings_view.append({
            "code": hcode, "name": hname,
            "cost": cost, "price": hprice, "pnl_pct": pnl_pct,
            "today_pct": today_pct, "signal": signal,
            "buy_point": buy_point, "stop_loss": stop_loss,
        })

    # 市场情绪：关注股涨跌分布
    all_pcts = [c["today_pct"] for c in candidates if c.get("today_pct") is not None]
    n_up   = sum(1 for p in all_pcts if p > 0)
    n_down = sum(1 for p in all_pcts if p < 0)
    sentiment = {
        "n_up": n_up, "n_down": n_down,
        "avg_pct": sum(all_pcts) / len(all_pcts) if all_pcts else None,
        "n_total": len(all_pcts),
    }

    # 今日操作建议：从持仓信号提炼
    suggestions = []
    for h in holdings_view:
        if h.get("signal"):
            suggestions.append(f"【{h['name']}（{h['code']}）】{h['signal']}")

    text = build_daily_text(today, top, holdings_view)
    print("\n" + text + "\n")

    if dry_run:
        print("[run_daily] --dry-run，未推送")
    else:
        card = build_daily_card(today, top, holdings_view, sentiment=sentiment, suggestions=suggestions)
        r = send_feishu_card(card)
        if r.get("sent"):
            print("[run_daily] 卡片推送成功")
        else:
            print(f"[run_daily] 卡片推送失败({r})，降级文本推送")
            print("[run_daily] 推送结果:", send_feishu(text))


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
