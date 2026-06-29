#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股全市场选股扫描。

流程：
  1. 批量拉取全市场行情 + 基本面（3次API调用搞定所有股票）
  2. 第一轮过滤：市值 / 成交额 / PE（config.SCREEN）
  3. 第二轮：对候选股拉财报（income/fina_indicator/cashflow）+ 技术买点
  4. 应用 passes_basic + score_stock + 降权护栏，输出 Top N

需要 TUSHARE_TOKEN 环境变量（已在 cmd.py 启动时从 .env 加载）。
仅供研究学习，不构成投资建议。
"""
from __future__ import annotations
import os, datetime as dt
from typing import List, Dict, Optional
import pandas as pd


def run_market_screen(sector_kw: str = "", top_n: int = 10, deep_n: int = 40) -> str:
    """
    sector_kw : 行业关键词，如 "半导体"。空字符串 = 全市场。
    top_n     : 最终展示数量。
    deep_n    : 第二轮财报分析上限（控制 API 调用量和耗时）。
    """
    from buy_point import calculate_buy_point
    from screener import passes_basic, score_stock
    from config import SCREEN
    from data_source import get_source, Quote

    # ── Tushare 初始化 ─────────────────────────────────────────────────────
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        return "⚠️ 选股需要 Tushare Token\n请在 .env 中配置 TUSHARE_TOKEN=xxx"

    try:
        import tushare as ts
        ts.set_token(token)
        pro = ts.pro_api()
    except Exception as e:
        return f"❌ Tushare 初始化失败: {e}"

    today = dt.date.today()
    src   = get_source()
    label = f"行业: {sector_kw}" if sector_kw else "A股全市场"
    print(f"[选股] 开始扫描 {label}...")

    # ── 批量拉取：日行情 + 基本面（共2次API调用，覆盖全市场）─────────────
    trade_date = ""
    daily_df = basic_df = None
    for offset in range(5):
        d = (today - dt.timedelta(days=offset)).strftime("%Y%m%d")
        try:
            dd = pro.daily(trade_date=d, fields="ts_code,close,amount,pct_chg")
            db = pro.daily_basic(trade_date=d, fields="ts_code,pe_ttm,total_mv")
            if dd is not None and not dd.empty:
                daily_df, basic_df, trade_date = dd, db, d
                break
        except Exception:
            pass

    if daily_df is None or daily_df.empty:
        return "❌ 无法获取市场数据，请检查网络或等待数据更新"

    merged = daily_df.merge(basic_df, on="ts_code", how="inner")

    # ── 可选：按行业过滤 ───────────────────────────────────────────────────
    name_map: Dict[str, str] = {}
    if sector_kw or True:   # 始终拉名称，用于显示
        try:
            si = pro.stock_basic(exchange="", list_status="L",
                                 fields="ts_code,name,industry")
            if si is not None and not si.empty:
                name_map = dict(zip(si.ts_code, si.name))
                if sector_kw:
                    sector_codes = set(
                        si[si.industry.str.contains(sector_kw, na=False)].ts_code
                    )
                    merged = merged[merged.ts_code.isin(sector_codes)]
                    print(f"[选股] 行业 '{sector_kw}': {len(merged)} 只")
        except Exception as e:
            print(f"[选股] 行业过滤失败({e})，使用全市场")

    # ── 第一轮过滤：市值 / 成交额 / PE ────────────────────────────────────
    # Tushare: total_mv 万元, amount 万元
    cap_min = SCREEN["market_cap_min"] / 1e4
    cap_max = SCREEN["market_cap_max"] / 1e4
    amt_min = SCREEN["daily_amount_min"] / 1e4

    merged["total_mv"] = pd.to_numeric(merged["total_mv"], errors="coerce")
    merged["amount"]   = pd.to_numeric(merged["amount"],   errors="coerce")
    merged["pe_ttm"]   = pd.to_numeric(merged["pe_ttm"],   errors="coerce")

    filtered = merged[
        (merged.total_mv >= cap_min) &
        (merged.total_mv <= cap_max) &
        (merged.amount   >= amt_min) &
        (merged.pe_ttm   >  0) &
        (merged.pe_ttm   <= 100)
    ]

    candidates = filtered.nlargest(deep_n, "amount")
    print(f"[选股] 初筛 {len(filtered)} 只 → 深度分析 {len(candidates)} 只")

    # ── 第二轮：财报 + 技术面评分 ─────────────────────────────────────────
    results: List[Dict] = []

    for idx, (_, row) in enumerate(candidates.iterrows(), 1):
        ts_code = row["ts_code"]
        code    = ts_code.split(".")[0]

        try:
            # 直接用批量数据构造 Quote（省掉 get_quote 的单股 API 调用）
            q = Quote(
                code=code,
                name=name_map.get(ts_code, code),
                price=float(row.get("close") or 0),
                pct_change=float(row.get("pct_chg") or 0),
                amount=float(row.get("amount") or 0) * 1e4,    # 万元→元
                market_cap=float(row.get("total_mv") or 0) * 1e4,
                pe_ttm=float(row["pe_ttm"]) if row["pe_ttm"] > 0 else None,
            )
            if not q.price:
                continue

            prices = src.get_daily(code, "A", 252)
            f      = src.get_financials(code, "A")

            if not prices:
                continue

            # 1年涨幅（用于降权护栏）
            price_1y_pct: Optional[float] = None
            if len(prices) >= 200 and prices[0]:
                price_1y_pct = (prices[-1] - prices[0]) / prices[0]

            flags = {"pe_percentile": None, "price_1y_pct": price_1y_pct}

            basic = passes_basic(q, f)
            sc    = score_stock(q, f, flags)
            bp    = calculate_buy_point(prices[-120:], f.eps_ttm)

            results.append({
                "code":          code,
                "name":          q.name,
                "price":         q.price,
                "pct":           q.pct_change,
                "pe":            q.pe_ttm,
                "score":         sc["score"],
                "hits":          sc["hits"],
                "basic_pass":    basic["pass"],
                "basic_reasons": basic.get("reasons", []),
                "skipped":       basic.get("skipped", []),
                "buy":           bp,
                "price_1y_pct":  price_1y_pct,
            })

            if idx % 10 == 0:
                print(f"[选股] 进度 {idx}/{len(candidates)}...")

        except Exception:
            pass

    if not results:
        return "⚠️ 未找到符合条件的股票（当前市场数据或网络问题）"

    # ── 排序：基础筛选通过优先，同层按得分降序 ────────────────────────────
    passed = sorted([r for r in results if r["basic_pass"]],
                    key=lambda x: x["score"], reverse=True)
    others = sorted([r for r in results if not r["basic_pass"]],
                    key=lambda x: x["score"], reverse=True)
    top = (passed + others)[:top_n]

    # ── 输出 ──────────────────────────────────────────────────────────────
    lines = [
        f"🔍 选股结果  {today}  {label}",
        f"扫描 {len(candidates)} 只 → 通过基础筛选 {len(passed)} 只\n",
    ]

    for i, r in enumerate(top, 1):
        status  = "✅" if r["basic_pass"] else "⬜"
        pe_str  = f"  PE={r['pe']:.0f}" if r["pe"] else ""
        pct_str = f"  {r['pct']:+.1f}%" if r["pct"] is not None else ""
        y1_str  = f"  1年{r['price_1y_pct']*100:+.0f}%" if r["price_1y_pct"] is not None else ""

        lines.append(
            f"\n{i}. {status} {r['name']}({r['code']})  "
            f"¥{r['price']:.2f}{pct_str}{pe_str}{y1_str}  得分{r['score']:+d}"
        )
        if r["hits"]:
            lines.append(f"   ✦ {' | '.join(r['hits'])}")
        if r["basic_reasons"]:
            lines.append(f"   ✗ {' | '.join(r['basic_reasons'])}")
        if r["skipped"]:
            lines.append(f"   ～ 跳过: {', '.join(r['skipped'])}")

        bp = r["buy"]
        if bp and not bp.get("error"):
            buy_pt = bp.get("buy_point")
            stop   = bp.get("stop_loss")
            target = bp.get("target_price")
            rr     = bp.get("risk_reward")
            trend  = ("↑" if bp.get("trend_up") else
                      "↓" if bp.get("trend_up") is False else "—")
            parts: List[str] = []
            if buy_pt: parts.append(f"买点¥{buy_pt:.2f}")
            if stop:   parts.append(f"止损¥{stop:.2f}")
            if target: parts.append(f"目标¥{target:.2f}")
            if rr:     parts.append(f"赔率{rr:.1f}x")
            lines.append(f"   趋势{trend}  {' | '.join(parts)}")

    lines.append(f"\n📌 `加股 <代码> <名称> A` 加入关注  `查 <代码>` 深入分析")
    lines.append("⚠️ 仅供研究学习，不构成投资建议")
    return "\n".join(lines)
