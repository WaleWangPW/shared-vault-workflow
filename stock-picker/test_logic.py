# -*- coding: utf-8 -*-
"""离线单元测试：纯逻辑部分（不触网）。运行: python3 test_logic.py"""
from buy_point import sma, trend_up, calculate_buy_point
from screener import passes_basic, score_stock, rank
from data_source import Quote, Financials
from push import build_daily_text


def test_sma_and_trend():
    up = list(range(1, 101))
    assert sma(up, 20) == sum(up[-20:]) / 20
    assert trend_up(up) is True
    down = list(range(100, 0, -1))
    assert trend_up(down) is False
    assert sma([1, 2], 60) is None
    print("✓ sma / trend_up")


def test_buy_point():
    assert "error" in calculate_buy_point([1, 2, 3])
    prices = [100 + i * 0.5 for i in range(120)]
    r = calculate_buy_point(prices, eps_ttm=2.24)
    assert r["buy_point"] > 0
    assert r["stop_loss"] == round(r["buy_point"] * 0.85, 3)
    assert r["target_price"] == round(2.24 * 30, 3)
    assert r["trend_up"] is True
    assert r["stop_loss"] < r["buy_point"]
    print("✓ calculate_buy_point", r)


def test_screener_skip_when_no_financials():
    q = Quote(code="688008", market_cap=300e8, amount=1e8)
    f = Financials(code="688008")
    res = passes_basic(q, f)
    assert res["pass"] is True
    assert "营收增速" in res["skipped"] and "净利增速" in res["skipped"]
    print("✓ passes_basic (akshare-only skip)", res)


def test_screener_reject_on_bad_financials():
    q = Quote(code="x", market_cap=300e8, amount=1e8)
    f = Financials(code="x", revenue_growth_yoy=0.10, profit_growth_yoy=0.10,
                   operating_cashflow=-5)
    res = passes_basic(q, f)
    assert res["pass"] is False
    assert len(res["reasons"]) >= 3
    print("✓ passes_basic (reject)", res)


def test_score_and_rank():
    q = Quote(code="x", ps_ttm=3.0)
    f = Financials(code="x", revenue_growth_yoy=1.5, rd_ratio=0.20,
                   gross_margin_series=[0.30, 0.35, 0.40])
    flags = {"insider_buying": True, "new_institution_survey": True}
    sc = score_stock(q, f, flags)
    assert sc["score"] == 55, sc
    ranked = rank([{"score": 1}, {"score": 9}, {"score": 5}], top_n=2)
    assert [c["score"] for c in ranked] == [9, 5]
    print("✓ score_stock / rank", sc)


def test_penalty_overvalued():
    q = Quote(code="688008", ps_ttm=20.0)
    f = Financials(code="688008", rd_ratio=0.20)
    flags = {"pe_percentile": 0.95, "price_1y_pct": 2.31}
    sc = score_stock(q, f, flags)
    assert sc["score"] == -30, sc
    assert any("PE>90%" in h for h in sc["hits"])

    flags2 = {"pe_percentile": 0.85, "price_1y_pct": 3.5}
    sc2 = score_stock(q, f, flags2)
    assert sc2["score"] == -25, sc2
    print("✓ penalty (澜起式过度定价降权)", sc, sc2)


def test_push_text():
    txt = build_daily_text("2026-06-26",
                           [{"name": "澜起科技", "code": "688008", "score": 30,
                             "hits": ["研发>15%"],
                             "buy": {"current": 258, "buy_point": 245, "stop_loss": 208}}],
                           [])
    assert "选股日报" in txt and "不构成投资建议" in txt
    print("✓ build_daily_text")


if __name__ == "__main__":
    test_sma_and_trend()
    test_buy_point()
    test_screener_skip_when_no_financials()
    test_screener_reject_on_bad_financials()
    test_score_and_rank()
    test_penalty_overvalued()
    test_push_text()
    print("\n全部通过 ✅")
