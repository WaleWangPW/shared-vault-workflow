# -*- coding: utf-8 -*-
"""
选股引擎 —— 基础筛选 + 隐形股票加分排序。
纯逻辑（score_stock / passes_basic）可离线单元测试。
仅供研究，非投资建议。
"""
from __future__ import annotations
from typing import Optional, Dict, List
from config import SCREEN, SCORE_WEIGHTS, PENALTY
from data_source import Quote, Financials


def passes_basic(q: Quote, f: Financials) -> Dict:
    """
    第一层硬性筛选。返回 {"pass": bool, "reasons": [...], "skipped": [...]}。
    无财务数据（AKShare-only）时，相关条件计入 skipped 而非判负。
    """
    reasons, skipped = [], []
    ok = True

    # ── ST / 退市风险股（最高优先级，直接拒绝）──────────────────────────
    if SCREEN.get("exclude_st", True) and q.name:
        n = q.name.strip()
        if n.startswith(("ST", "*ST")) or n.startswith("S*") or "退市" in n[:6]:
            return {"pass": False, "reasons": ["ST/风险警示股"], "skipped": []}

    # ── 市值 ─────────────────────────────────────────────────────────────
    if q.market_cap:
        if not (SCREEN["market_cap_min"] <= q.market_cap <= SCREEN["market_cap_max"]):
            ok = False
            reasons.append(f"市值 {q.market_cap/1e8:.0f}亿 不在区间")
    else:
        skipped.append("市值")

    # ── 成交额 ───────────────────────────────────────────────────────────
    if q.amount:
        if q.amount < SCREEN["daily_amount_min"]:
            ok = False
            reasons.append("成交额不足")
    else:
        skipped.append("成交额")

    # ── 营收增速 ─────────────────────────────────────────────────────────
    if f.revenue_growth_yoy is not None:
        if f.revenue_growth_yoy < SCREEN["revenue_growth_yoy_min"]:
            ok = False
            reasons.append("营收增速不足")
    else:
        skipped.append("营收增速")

    # ── 净利润增速 ───────────────────────────────────────────────────────
    if f.profit_growth_yoy is not None:
        if f.profit_growth_yoy < SCREEN["profit_growth_yoy_min"]:
            ok = False
            reasons.append("净利增速不足")
    else:
        skipped.append("净利增速")

    # ── 经营现金流 ───────────────────────────────────────────────────────
    if SCREEN["operating_cashflow_positive"] and f.operating_cashflow is not None:
        if f.operating_cashflow <= 0:
            ok = False
            reasons.append("经营现金流为负")
    elif f.operating_cashflow is None:
        skipped.append("经营现金流")

    # ── OCF/净利润 极端过滤（<0.5 → 严重现金流造假信号）──────────────────
    ocf_ni_floor = SCREEN.get("ocf_ni_ratio_min")
    if (ocf_ni_floor is not None
            and f.operating_cashflow is not None
            and f.net_profit is not None and f.net_profit > 0):
        ocf_ni = f.operating_cashflow / f.net_profit
        if ocf_ni < ocf_ni_floor:
            ok = False
            reasons.append(f"现金流质量极差(OCF/NI={ocf_ni:.2f})")
    elif f.net_profit is None:
        skipped.append("OCF/NI")

    # ── 核心利润比例 极端过滤（<50% → 严重依赖非经常性收益）──────────────
    core_floor = SCREEN.get("core_profit_ratio_min")
    if core_floor is not None and f.core_profit_ratio is not None:
        if f.core_profit_ratio < core_floor:
            ok = False
            reasons.append(f"核心利润占比低({f.core_profit_ratio:.0%})")
    elif f.core_profit_ratio is None:
        skipped.append("扣非比例")

    return {"pass": ok, "reasons": reasons, "skipped": skipped}


def score_stock(q: Quote, f: Financials, flags: Optional[Dict] = None) -> Dict:
    """
    第二层加分。flags 含 pe_percentile / price_1y_pct / 外部信号。
    AKShare-only 模式下多为 None，不加分也不扣分。
    """
    flags = flags or {}
    score = 0
    hits: List[str] = []
    w = SCORE_WEIGHTS

    # ── 原有因子 ──────────────────────────────────────────────────────────

    if (q.ps_ttm is not None and q.ps_ttm < 5
            and f.revenue_growth_yoy is not None and f.revenue_growth_yoy > 1.0):
        score += w["ps_lt5_rev_gt100"]; hits.append("PS<5且营收>100%")

    if f.rd_ratio is not None and f.rd_ratio > 0.15:
        score += w["rd_ratio_gt15"]; hits.append("研发>15%")

    gm = f.gross_margin_series
    if len(gm) >= 3 and gm[-1] > gm[-2] > gm[-3]:
        score += w["gross_margin_3q_up"]; hits.append("毛利率连升3季")

    if flags.get("ocf_improving"):
        score += w["ocf_improving"]; hits.append("现金流改善")
    if flags.get("new_institution_survey"):
        score += w["new_institution_survey"]; hits.append("新增机构调研")
    if flags.get("insider_buying"):
        score += w["insider_buying"]; hits.append("高管增持")
    if flags.get("analyst_coverage_0to1"):
        score += w["analyst_coverage_0to1"]; hits.append("分析师0→1")
    if flags.get("industry_uptrend"):
        score += w["industry_uptrend"]; hits.append("行业景气上升")

    # ── 质量因子（新增）──────────────────────────────────────────────────

    # ROE 趋势（连续3季提升）
    roe = f.roe_series
    if len(roe) >= 3 and roe[-1] > roe[-2] > roe[-3]:
        score += w.get("roe_trend_up_3q", 0); hits.append("ROE连升3季")
    if roe and roe[-1] >= 0.15:
        score += w.get("roe_gt15", 0); hits.append(f"ROE≥15%({roe[-1]*100:.0f}%)")

    # OCF/净利润质量（既加分也扣分）
    if (f.operating_cashflow is not None
            and f.net_profit is not None and f.net_profit > 0):
        ocf_ni = f.operating_cashflow / f.net_profit
        if ocf_ni >= 1.2:
            score += w.get("ocf_ni_gt12", 0)
            hits.append(f"现金流优质({ocf_ni:.1f}x)")
        elif ocf_ni < 0.8:
            score += PENALTY.get("ocf_ni_lt08", 0)
            hits.append(f"⚠现金流差({ocf_ni:.1f}x)")

    # 扣非净利质量（既加分也扣分）
    if f.core_profit_ratio is not None:
        if f.core_profit_ratio >= 0.9:
            score += w.get("core_profit_high", 0)
            hits.append(f"主业贡献高({f.core_profit_ratio:.0%})")
        elif f.core_profit_ratio < 0.7:
            score += PENALTY.get("core_profit_lt07", 0)
            hits.append(f"⚠利润含水份({f.core_profit_ratio:.0%})")

    # ── 降权护栏（澜起教训：过度定价 → 扣分）──────────────────────────
    pe_pct = flags.get("pe_percentile")   # 0~1
    if pe_pct is not None:
        if pe_pct > 0.90:
            score += PENALTY["pe_percentile_gt80"] + PENALTY["pe_percentile_gt90"]
            hits.append("⚠PE>90%分位")
        elif pe_pct > 0.80:
            score += PENALTY["pe_percentile_gt80"]
            hits.append("⚠PE>80%分位")

    p1y = flags.get("price_1y_pct")       # 3.0 = +300%
    if p1y is not None:
        if p1y > 3.0:
            score += PENALTY["price_1y_gt300pct"]
            hits.append("⚠一年涨>300%")
        elif p1y > 2.0:
            score += PENALTY.get("price_1y_gt200pct", 0)
            hits.append("⚠一年涨>200%")

    return {"score": score, "hits": hits}


def rank(candidates: List[Dict], top_n: int = 15) -> List[Dict]:
    """candidates: [{quote, financials, score, ...}]，按 score 降序取 top_n。"""
    return sorted(candidates, key=lambda c: c.get("score", 0), reverse=True)[:top_n]
