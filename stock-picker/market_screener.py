#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多市场选股扫描（A股 / 港股 / 美股）。

用法（通过 cmd.py）：
  选股           → A 股全市场（默认）
  选股 A         → A 股全市场
  选股 HK        → 港股
  选股 US        → 美股
  选股 ALL       → 三市合并输出
  选股 半导体     → A 股 + 行业关键词过滤

仅供研究学习，不构成投资建议。
"""
from __future__ import annotations
import os, datetime as dt
from typing import List, Dict, Optional
import pandas as pd


# Nasdaq 100 核心 + 关键 S&P 500 龙头（约 80 只，覆盖科技/金融/医疗）
US_UNIVERSE: List[str] = [
    # 科技/半导体
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO",
    "AMD", "QCOM", "INTC", "AMAT", "TXN", "MU", "ADI", "LRCX", "KLAC",
    "NXPI", "MRVL", "MCHP", "ON", "SMCI", "ARM",
    # 互联网/软件/SaaS
    "NFLX", "INTU", "CSCO", "BKNG", "PANW", "SNPS", "CDNS", "CRWD",
    "ADSK", "ZS", "WDAY", "TEAM", "TTD", "DDOG", "NET", "MDB", "SNOW",
    "PLTR", "ABNB", "APP", "UBER", "SHOP", "OKTA",
    # 消费/零售
    "COST", "CTAS", "ROST", "PAYX", "FAST", "CPRT",
    # 医疗/生物
    "ISRG", "REGN", "VRTX", "DXCM", "IDXX", "LLY", "JNJ", "UNH",
    "PFE", "ABBV", "MRNA",
    # 金融/支付/加密
    "JPM", "BAC", "GS", "MS", "V", "MA", "PYPL", "COIN", "MSTR",
    # 其他
    "RBLX", "HOOD", "CRCL",
]


# ── 公共：格式化单条结果 ────────────────────────────────────────────────────

def _fmt_result(r: Dict, currency: str = "¥") -> List[str]:
    status  = "✅" if r["basic_pass"] else "⬜"
    pe_str  = f"  PE={r['pe']:.0f}" if r.get("pe") else ""
    pct_str = f"  {r['pct']:+.1f}%" if r.get("pct") is not None else ""
    y1_str  = (f"  1年{r['price_1y_pct']*100:+.0f}%"
               if r.get("price_1y_pct") is not None else "")
    lines = [
        f"\n{r['rank']}. {status} {r['name']}({r['code']})  "
        f"{currency}{r['price']:.2f}{pct_str}{pe_str}{y1_str}  得分{r['score']:+d}"
    ]
    if r.get("hits"):
        lines.append(f"   ✦ {' | '.join(r['hits'])}")
    if r.get("basic_reasons"):
        lines.append(f"   ✗ {' | '.join(r['basic_reasons'])}")
    if r.get("skipped"):
        lines.append(f"   ～ 跳过: {', '.join(r['skipped'])}")
    bp = r.get("buy")
    if bp and not bp.get("error"):
        buy_pt = bp.get("buy_point")
        stop   = bp.get("stop_loss")
        target = bp.get("target_price")
        rr     = bp.get("risk_reward")
        trend  = ("↑" if bp.get("trend_up") else
                  "↓" if bp.get("trend_up") is False else "—")
        parts: List[str] = []
        if buy_pt: parts.append(f"买点{currency}{buy_pt:.2f}")
        if stop:   parts.append(f"止损{currency}{stop:.2f}")
        if target: parts.append(f"目标{currency}{target:.2f}")
        if rr and rr > 0: parts.append(f"赔率{rr:.1f}x")
        lines.append(f"   趋势{trend}  {' | '.join(parts)}")
    return lines


def _rank_and_slice(results: List[Dict], top_n: int):
    passed = sorted([r for r in results if r["basic_pass"]],
                    key=lambda x: x["score"], reverse=True)
    others = sorted([r for r in results if not r["basic_pass"]],
                    key=lambda x: x["score"], reverse=True)
    top = (passed + others)[:top_n]
    for i, r in enumerate(top, 1):
        r["rank"] = i
    return top, len(passed)


def _score_lite(price: float, pct_day: float, bp: Dict,
                price_1y_pct: Optional[float]) -> Dict:
    """港股 / 美股纯技术面轻量评分。"""
    from config import PENALTY
    score = 0
    hits: List[str] = []

    if bp and not bp.get("error"):
        trend  = bp.get("trend_up")
        buy_pt = bp.get("buy_point")
        stop   = bp.get("stop_loss")
        if trend:
            score += 10; hits.append("↑趋势")
        elif trend is False:
            score -= 5; hits.append("↓趋势")
        if buy_pt and price:
            diff = (price - buy_pt) / buy_pt
            if abs(diff) <= 0.03:
                score += 15; hits.append("📍近买点")
            elif diff < -0.10:
                score -= 5
        if stop and price <= stop:
            score -= 20; hits.append("🔴破止损")
        elif stop and price and (price - stop) / stop < 0.08:
            hits.append(f"⚠距止损{(price-stop)/stop*100:.0f}%")

    if pct_day > 3:
        score += 5; hits.append(f"强势+{pct_day:.1f}%")
    elif pct_day < -3:
        score -= 5; hits.append(f"大跌{pct_day:.1f}%")

    if price_1y_pct is not None:
        if price_1y_pct > 3.0:
            score += PENALTY.get("price_1y_gt300pct", 0); hits.append("⚠一年涨>300%")
        elif price_1y_pct > 2.0:
            score += PENALTY.get("price_1y_gt200pct", 0); hits.append("⚠一年涨>200%")

    return {"score": score, "hits": hits}


# ── A 股 ──────────────────────────────────────────────────────────────────────

def screen_a(top_n: int = 10, deep_n: int = 40, sector_kw: str = "") -> str:
    """A 股全市场选股（Tushare 批量行情 + 财报 + 全量质量因子）。"""
    from buy_point import calculate_buy_point
    from screener import passes_basic, score_stock
    from config import SCREEN_A as SCREEN
    from data_source import get_source, Quote

    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        return "⚠️ A股选股需要 Tushare Token，请在 .env 配置 TUSHARE_TOKEN=xxx", [], 0
    try:
        import tushare as ts
        ts.set_token(token)
        pro = ts.pro_api()
    except Exception as e:
        return f"❌ Tushare 初始化失败: {e}", [], 0

    today = dt.date.today()
    src   = get_source()
    label = f"行业:{sector_kw}" if sector_kw else "全市场"
    print(f"[选股A] 扫描 {label}...")

    # 批量拉行情（最近交易日，最多回溯5天）
    daily_df = basic_df = None
    for offset in range(5):
        d = (today - dt.timedelta(days=offset)).strftime("%Y%m%d")
        try:
            dd = pro.daily(trade_date=d, fields="ts_code,close,amount,pct_chg")
            db = pro.daily_basic(trade_date=d, fields="ts_code,pe_ttm,total_mv")
            if dd is not None and not dd.empty:
                daily_df, basic_df = dd, db
                break
        except Exception:
            pass

    if daily_df is None or daily_df.empty:
        return "❌ 无法获取A股行情数据，请检查网络", [], 0

    merged = daily_df.merge(basic_df, on="ts_code", how="inner")

    # 名称 + 行业过滤
    name_map: Dict[str, str] = {}
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
                print(f"[选股A] 行业 '{sector_kw}': {len(merged)} 只")
    except Exception as e:
        print(f"[选股A] 名称/行业拉取失败({e})")

    # 第一轮数值过滤
    for col in ("total_mv", "amount", "pe_ttm"):
        merged[col] = pd.to_numeric(merged[col], errors="coerce")

    cap_min = SCREEN["market_cap_min"] / 1e4
    cap_max = SCREEN["market_cap_max"] / 1e4
    amt_min = SCREEN["daily_amount_min"] / 1e4

    filtered = merged[
        (merged.total_mv >= cap_min) &
        (merged.total_mv <= cap_max) &
        (merged.amount   >= amt_min) &
        (merged.pe_ttm   >  0) &
        (merged.pe_ttm   <= 100)
    ]
    candidates = filtered.nlargest(deep_n, "amount")
    print(f"[选股A] 初筛 {len(filtered)} 只 → 深度分析 {len(candidates)} 只")

    results: List[Dict] = []
    for idx, (_, row) in enumerate(candidates.iterrows(), 1):
        ts_code = row["ts_code"]
        code    = ts_code.split(".")[0]
        try:
            q = Quote(
                code=code,
                name=name_map.get(ts_code, code),
                price=float(row.get("close") or 0),
                pct_change=float(row.get("pct_chg") or 0),
                amount=float(row.get("amount") or 0) * 1e4,
                market_cap=float(row.get("total_mv") or 0) * 1e4,
                pe_ttm=float(row["pe_ttm"]) if row["pe_ttm"] > 0 else None,
            )
            if not q.price:
                continue
            prices = src.get_daily(code, "A", 252)
            f_data = src.get_financials(code, "A")
            if not prices:
                continue
            price_1y_pct: Optional[float] = None
            if len(prices) >= 200 and prices[0]:
                price_1y_pct = (prices[-1] - prices[0]) / prices[0]
            flags = {"pe_percentile": None, "price_1y_pct": price_1y_pct}
            basic = passes_basic(q, f_data)
            sc    = score_stock(q, f_data, flags)
            bp    = calculate_buy_point(prices[-120:], f_data.eps_ttm)
            results.append({
                "code": code, "name": q.name, "price": q.price,
                "pct": q.pct_change, "pe": q.pe_ttm, "score": sc["score"],
                "hits": sc["hits"], "basic_pass": basic["pass"],
                "basic_reasons": basic.get("reasons", []),
                "skipped": basic.get("skipped", []),
                "buy": bp, "price_1y_pct": price_1y_pct,
            })
            if idx % 10 == 0:
                print(f"[选股A] 进度 {idx}/{len(candidates)}...")
        except Exception:
            pass

    if not results:
        return "⚠️ A股: 未找到符合条件的股票", [], 0

    top, n_passed = _rank_and_slice(results, top_n)
    n_scanned = len(candidates)
    lines = [
        f"🇨🇳 A股选股  {today}  {label}",
        f"扫描 {n_scanned} 只 → 通过基础筛选 {n_passed} 只\n",
    ]
    for r in top:
        lines.extend(_fmt_result(r, "¥"))
    lines.append("\n📌 `加股 <代码> <名称> A` 加入关注  `查 <代码>` 深入分析")
    lines.append("⚠️ 仅供研究学习，不构成投资建议")
    return "\n".join(lines), top, n_scanned


# ── 港股 ──────────────────────────────────────────────────────────────────────

def screen_hk(top_n: int = 10, deep_n: int = 30) -> tuple:
    """港股选股：AKShare 全港行情 → 批量 yfinance 历史 → 技术面评分。"""
    from buy_point import calculate_buy_point
    from config import SCREEN_HK

    today = dt.date.today()
    print("[选股HK] 拉取港股全市场行情...")

    try:
        import akshare as ak
        spot = ak.stock_hk_spot_em()
    except Exception as e:
        return f"❌ 港股行情拉取失败: {e}", [], 0

    if spot is None or spot.empty:
        return "❌ 港股行情数据为空", [], 0

    for col in ("成交额", "市盈率(静)", "最新价", "总市值"):
        if col in spot.columns:
            spot[col] = pd.to_numeric(spot[col], errors="coerce")

    amt_min = SCREEN_HK.get("daily_amount_min", 0)
    pe_max  = SCREEN_HK.get("pe_ttm_max", 80)

    filtered = spot[spot["成交额"].fillna(0) >= amt_min].copy()
    if "市盈率(静)" in filtered.columns:
        filtered = filtered[
            (filtered["市盈率(静)"].fillna(0) > 0) &
            (filtered["市盈率(静)"] < pe_max)
        ]
    if "总市值" in filtered.columns and SCREEN_HK.get("market_cap_min"):
        filtered = filtered[filtered["总市值"].fillna(0) >= SCREEN_HK["market_cap_min"]]

    candidates = filtered.nlargest(deep_n, "成交额")
    print(f"[选股HK] 初筛 {len(filtered)} 只 → 深度分析 {len(candidates)} 只")

    # 构建 yfinance 代码映射并批量拉历史
    yf_to_row: Dict[str, Dict] = {}
    yf_codes: List[str] = []
    for _, row in candidates.iterrows():
        raw_code = str(row.get("代码", "")).strip()
        try:
            yf_code = f"{int(raw_code):04d}.HK"
            yf_to_row[yf_code] = {"ak_code": raw_code, "row": row}
            yf_codes.append(yf_code)
        except ValueError:
            pass

    if not yf_codes:
        return "⚠️ 港股: 无有效代码", [], 0

    try:
        import yfinance as yf
        raw = yf.download(yf_codes, period="252d", progress=False, auto_adjust=True)
    except Exception as e:
        return f"❌ 港股历史数据拉取失败: {e}", [], 0

    # 解析收盘价
    def _get_closes(ticker: str) -> List[float]:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                return raw["Close"][ticker].dropna().tolist()
            return raw["Close"].dropna().tolist()
        except Exception:
            return []

    results: List[Dict] = []
    for yf_code, meta in yf_to_row.items():
        row      = meta["row"]
        ak_code  = meta["ak_code"]
        prices   = _get_closes(yf_code)
        if len(prices) < 20:
            continue

        price  = float(row.get("最新价") or (prices[-1] if prices else 0))
        pct    = float(row.get("涨跌幅") or 0)
        pe     = float(row.get("市盈率(静)") or 0) or None
        name   = str(row.get("名称", ak_code))

        price_1y_pct: Optional[float] = None
        if len(prices) >= 200:
            price_1y_pct = (prices[-1] - prices[0]) / prices[0]

        bp = calculate_buy_point(prices[-120:])
        sc = _score_lite(price, pct, bp, price_1y_pct)

        results.append({
            "code": ak_code, "name": name, "price": price,
            "pct": pct, "pe": pe, "score": sc["score"], "hits": sc["hits"],
            "basic_pass": True, "basic_reasons": [], "skipped": ["财报(HK轻量)"],
            "buy": bp, "price_1y_pct": price_1y_pct,
        })

    if not results:
        return "⚠️ 港股: 历史数据不足，无法生成结果", [], 0

    top, _ = _rank_and_slice(results, top_n)
    n_scanned = len(candidates)
    lines = [
        f"🇭🇰 港股选股  {today}",
        f"扫描 {n_scanned} 只 → 得分前 {len(top)} 只（纯技术面）\n",
    ]
    for r in top:
        lines.extend(_fmt_result(r, "HK$"))
    lines.append("\n📌 `加股 <代码> <名称> HK` 加入关注")
    lines.append("⚠️ 港股为技术面评分，无A股财报深度。仅供研究，非投资建议")
    return "\n".join(lines), top, n_scanned


# ── 美股 ──────────────────────────────────────────────────────────────────────

def screen_us(top_n: int = 10, deep_n: int = 30) -> tuple:
    """美股选股：Nasdaq100/S&P500 Universe → yfinance 批量历史 → 技术面评分。"""
    from buy_point import calculate_buy_point

    today = dt.date.today()
    print(f"[选股US] 扫描 {len(US_UNIVERSE)} 只美股标的...")

    try:
        import yfinance as yf
        raw = yf.download(
            US_UNIVERSE, period="252d",
            progress=False, auto_adjust=True
        )
    except Exception as e:
        return f"❌ 美股数据拉取失败: {e}", [], 0

    # 解析每只票收盘价
    def _get_closes(ticker: str) -> List[float]:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                return raw["Close"][ticker].dropna().tolist()
            return raw["Close"].dropna().tolist()
        except Exception:
            return []

    price_map: Dict[str, List[float]] = {}
    for ticker in US_UNIVERSE:
        closes = _get_closes(ticker)
        if len(closes) >= 20:
            price_map[ticker] = closes

    print(f"[选股US] 有效标的 {len(price_map)} 只")

    # 按近30日正向动量排序，取 top deep_n
    def _momentum(closes: List[float]) -> float:
        if len(closes) < 30:
            return 0.0
        return (closes[-1] - closes[-30]) / closes[-30]

    ranked = sorted(
        price_map.items(),
        key=lambda kv: _momentum(kv[1]),
        reverse=True
    )
    candidates = ranked[:deep_n]
    print(f"[选股US] 深度分析 {len(candidates)} 只")

    results: List[Dict] = []
    for ticker, prices in candidates:
        price = prices[-1]
        pct   = _momentum(prices) * 100 / 30   # 粗略日均

        price_1y_pct: Optional[float] = None
        if len(prices) >= 200:
            price_1y_pct = (prices[-1] - prices[0]) / prices[0]

        bp = calculate_buy_point(prices[-120:])
        sc = _score_lite(price, pct, bp, price_1y_pct)

        # PE（单股调用，可选）
        pe = None
        try:
            info = yf.Ticker(ticker).fast_info
            pe   = getattr(info, "pe_ratio", None)
        except Exception:
            pass

        results.append({
            "code": ticker, "name": ticker, "price": price,
            "pct": pct, "pe": pe, "score": sc["score"], "hits": sc["hits"],
            "basic_pass": True, "basic_reasons": [], "skipped": ["财报(US轻量)"],
            "buy": bp, "price_1y_pct": price_1y_pct,
        })

    if not results:
        return "⚠️ 美股: 未找到数据", [], 0

    top, _ = _rank_and_slice(results, top_n)
    n_scanned = len(price_map)
    lines = [
        f"🇺🇸 美股选股  {today}",
        f"扫描 {n_scanned} 只 → 得分前 {len(top)} 只（纯技术面）\n",
    ]
    for r in top:
        lines.extend(_fmt_result(r, "$"))
    lines.append("\n📌 `加股 <代码> <名称> US` 加入关注")
    lines.append("⚠️ 美股为技术面评分，无A股财报深度。仅供研究，非投资建议")
    return "\n".join(lines), top, n_scanned


# ── 主入口 ───────────────────────────────────────────────────────────────────

def run_market_screen(market: str = "A", sector_kw: str = "",
                      top_n: int = 10, deep_n: int = 40,
                      structured: bool = False):
    """
    structured=False → 返回格式化文本（供 CLI 使用）
    structured=True  → 返回 (text, results, n_scanned)（供飞书卡片使用）
    """
    m = market.upper()
    if m == "HK":
        text, res, n = screen_hk(top_n=top_n, deep_n=min(deep_n, 30))
    elif m == "US":
        text, res, n = screen_us(top_n=top_n, deep_n=min(deep_n, 30))
    elif m in ("ALL", "全部"):
        ta, ra, na = screen_a(top_n=top_n, deep_n=deep_n, sector_kw=sector_kw)
        th, rh, nh = screen_hk(top_n=top_n, deep_n=min(deep_n, 20))
        tu, ru, nu = screen_us(top_n=top_n, deep_n=min(deep_n, 20))
        sep = "\n" + "─" * 40 + "\n"
        text = sep.join([ta, th, tu])
        res, n = [], na + nh + nu  # ALL 模式不合并 results（市场不同）
    else:
        kw = sector_kw if m == "A" else market
        text, res, n = screen_a(top_n=top_n, deep_n=deep_n, sector_kw=kw)

    if structured:
        return text, res, n
    return text
