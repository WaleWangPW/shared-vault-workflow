# -*- coding: utf-8 -*-
"""
数据源抽象层。

- AKShareSource：免费，A 股行情 + 基础估值（东财/新浪）。无 token。
- YFinanceSource：免费，HK/US 行情（Yahoo Finance，全球可用）。无 token。
- TushareSource：付费 ¥1000/年，A 股财报 + 估值 + 机构持仓。需 TUSHARE_TOKEN。
- HybridSource：A 股用 AKShare，HK/US 自动切换 yfinance（推荐）。

get_source() 优先级：
  有 TUSHARE_TOKEN → TushareSource（A股财务）+ YFinanceSource（HK/US）
  无 token        → AKShareSource（A股）+ YFinanceSource（HK/US）
"""
from __future__ import annotations
import os
import datetime as dt
from dataclasses import dataclass, field
from typing import Optional, List
import pandas as pd


@dataclass
class Quote:
    code: str
    name: str = ""
    price: float = 0.0
    pct_change: float = 0.0
    amount: float = 0.0          # 成交额（元）
    market_cap: float = 0.0      # 总市值（元）
    pe_ttm: Optional[float] = None
    ps_ttm: Optional[float] = None


@dataclass
class Financials:
    code: str
    revenue_growth_yoy: Optional[float] = None   # 营收同比，0.30 = +30%
    profit_growth_yoy: Optional[float] = None    # 净利润同比
    gross_margin_series: List[float] = field(default_factory=list)  # 近几季毛利率（升序，小数）
    operating_cashflow: Optional[float] = None   # 经营活动现金流（元）
    rd_ratio: Optional[float] = None             # 研发费用/营收
    eps_ttm: Optional[float] = None              # 每股收益 TTM
    forward_pe: Optional[float] = None
    peg: Optional[float] = None


class DataSource:
    """接口约定。"""
    name = "base"

    def get_quote(self, code: str, market: str) -> Optional[Quote]:
        raise NotImplementedError

    def get_daily(self, code: str, market: str, days: int = 120) -> List[float]:
        """返回按日期升序的收盘价 list[float]，长度最多 days 条。"""
        raise NotImplementedError

    def get_financials(self, code: str, market: str) -> Financials:
        """无能力时返回全 None 的 Financials。"""
        return Financials(code=code)

    def get_pe_percentile(self, code: str, market: str, years: int = 3) -> Optional[float]:
        """当前 PE 在过去 N 年的历史分位（0~1）。不支持时返回 None。"""
        return None


# ---------------------------------------------------------------------------
# AKShare 免费源
# ---------------------------------------------------------------------------

class AKShareSource(DataSource):
    name = "akshare"

    def __init__(self):
        import akshare as ak
        self.ak = ak
        self._spot_df: Optional[pd.DataFrame] = None
        self._spot_date: str = ""
        self._hk_spot_df: Optional[pd.DataFrame] = None
        self._hk_spot_date: str = ""

    def _date_range(self, days: int):
        end = dt.date.today().strftime("%Y%m%d")
        start = (dt.date.today() - dt.timedelta(days=int(days * 1.6))).strftime("%Y%m%d")
        return start, end

    def _spot_cache(self) -> pd.DataFrame:
        """东方财富全量 A 股实时行情（同日复用）。"""
        today = dt.date.today().isoformat()
        if self._spot_df is None or self._spot_date != today:
            self._spot_df = self.ak.stock_zh_a_spot_em()
            self._spot_date = today
        return self._spot_df

    def _hk_spot_cache(self) -> pd.DataFrame:
        """东方财富港股实时行情（同日复用）。"""
        today = dt.date.today().isoformat()
        if self._hk_spot_df is None or self._hk_spot_date != today:
            self._hk_spot_df = self.ak.stock_hk_spot_em()
            self._hk_spot_date = today
        return self._hk_spot_df

    def get_daily(self, code: str, market: str, days: int = 120) -> List[float]:
        ak = self.ak
        start, end = self._date_range(days)
        if market == "A":
            df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                    start_date=start, end_date=end, adjust="qfq")
            return df["收盘"].astype(float).tolist()[-days:]
        if market == "HK":
            df = ak.stock_hk_hist(symbol=code, period="daily",
                                  start_date=start, end_date=end, adjust="qfq")
            return df["收盘"].astype(float).tolist()[-days:]
        if market == "US":
            df = ak.stock_us_hist(symbol=code, period="daily",
                                  start_date=start, end_date=end, adjust="qfq")
            return df["收盘"].astype(float).tolist()[-days:]
        raise ValueError(f"unsupported market {market}")

    def get_quote(self, code: str, market: str) -> Optional[Quote]:
        ak = self.ak
        try:
            if market == "A":
                start, end = self._date_range(5)
                hist = ak.stock_zh_a_hist(symbol=code, period="daily",
                                          start_date=start, end_date=end, adjust="qfq")
                price  = float(hist["收盘"].iloc[-1])
                amount = float(hist["成交额"].iloc[-1]) if "成交额" in hist.columns else 0.0
                pct_chg = float(hist["涨跌幅"].iloc[-1]) if "涨跌幅" in hist.columns else 0.0

                # 市值 / PE / 名称 —— 从全量实时行情缓存中取
                market_cap, pe_ttm, name = 0.0, None, ""
                try:
                    spot = self._spot_cache()
                    row = spot[spot["代码"] == code]
                    if not row.empty:
                        r = row.iloc[0]
                        name = str(r.get("名称", ""))
                        mc = r.get("总市值")
                        if mc is not None:
                            market_cap = float(mc)  # 单位：元
                        pe_raw = r.get("市盈率-动态")
                        if pe_raw is not None and str(pe_raw) not in ("-", "nan", "None", ""):
                            v = float(pe_raw)
                            pe_ttm = v if v > 0 else None
                except Exception:
                    pass

                return Quote(code=code, name=name,
                             price=price, pct_change=pct_chg,
                             amount=amount, market_cap=market_cap, pe_ttm=pe_ttm)
            elif market == "HK":
                # 从港股实时行情取名称/涨跌幅/成交额/PE
                name, pct_chg, amount, pe_ttm, price = "", 0.0, 0.0, None, 0.0
                try:
                    spot = self._hk_spot_cache()
                    # AKShare 港股代码列通常为 5 位字符串，如 "06809"
                    row = spot[spot["代码"] == code]
                    if not row.empty:
                        r = row.iloc[0]
                        name    = str(r.get("名称", ""))
                        price   = float(r.get("最新价") or 0)
                        pct_raw = r.get("涨跌幅")
                        if pct_raw is not None and str(pct_raw) not in ("", "nan", "None", "-"):
                            pct_chg = float(pct_raw)
                        amt = r.get("成交额")
                        if amt is not None:
                            amount = float(amt)
                        pe_raw = r.get("市盈率(静)") or r.get("市盈率")
                        if pe_raw is not None and str(pe_raw) not in ("", "nan", "None", "-"):
                            v = float(pe_raw)
                            pe_ttm = v if v > 0 else None
                except Exception:
                    pass
                if not price:
                    prices = self.get_daily(code, market, 2)
                    price = float(prices[-1]) if prices else 0.0
                return Quote(code=code, name=name, price=price,
                             pct_change=pct_chg, amount=amount, pe_ttm=pe_ttm)
            else:
                prices = self.get_daily(code, market, 2)
                return Quote(code=code, price=float(prices[-1]) if prices else 0.0)
        except Exception as e:
            print(f"[akshare] get_quote {code}: {e}")
            return None

    def get_financials(self, code: str, market: str) -> Financials:
        # AKShare 财报数据不稳定，降级交给 TushareSource
        return Financials(code=code)

    def get_pe_percentile(self, code: str, market: str, years: int = 3) -> Optional[float]:
        # AKShare 模式不支持历史 PE 分位计算，静默返回 None。
        # 需要 PE 历史分位请配置 TUSHARE_TOKEN。
        return None


# ---------------------------------------------------------------------------
# Tushare Pro 付费源
# ---------------------------------------------------------------------------

class TushareSource(DataSource):
    name = "tushare"

    def __init__(self, token: str):
        import tushare as ts
        ts.set_token(token)
        self.pro = ts.pro_api()
        self._ak: Optional[AKShareSource] = None

    def _ak_source(self) -> AKShareSource:
        if self._ak is None:
            self._ak = AKShareSource()
        return self._ak

    @staticmethod
    def _to_ts_code(code: str, market: str) -> str:
        if market == "HK":
            return code + ".HK"
        if market == "US":
            return code + ".O"
        # A 股：首字符判交易所
        if code.startswith(("6", "5", "9")):
            return code + ".SH"
        return code + ".SZ"

    def get_daily(self, code: str, market: str, days: int = 120) -> List[float]:
        if market != "A":
            return self._ak_source().get_daily(code, market, days)
        ts_code = self._to_ts_code(code, market)
        end = dt.date.today().strftime("%Y%m%d")
        start = (dt.date.today() - dt.timedelta(days=int(days * 1.6))).strftime("%Y%m%d")
        try:
            df = self.pro.daily(ts_code=ts_code, start_date=start, end_date=end)
            if df is None or df.empty:
                return self._ak_source().get_daily(code, market, days)
            df = df.sort_values("trade_date", ascending=True)
            return df["close"].astype(float).tolist()[-days:]
        except Exception as e:
            print(f"[tushare] daily fallback {code}: {e}")
            return self._ak_source().get_daily(code, market, days)

    def get_quote(self, code: str, market: str) -> Optional[Quote]:
        if market != "A":
            return self._ak_source().get_quote(code, market)
        ts_code = self._to_ts_code(code, market)
        for offset in range(5):
            trade_date = (dt.date.today() - dt.timedelta(days=offset)).strftime("%Y%m%d")
            try:
                df = self.pro.daily_basic(
                    ts_code=ts_code, trade_date=trade_date,
                    fields="ts_code,close,pe_ttm,pb,ps_ttm,total_mv,amount"
                )
                if df is not None and not df.empty:
                    row = df.iloc[0]

                    def _f(key) -> Optional[float]:
                        v = row.get(key)
                        try:
                            return float(v) if v is not None and str(v) not in ("", "nan", "None") else None
                        except Exception:
                            return None

                    return Quote(
                        code=code,
                        price=_f("close") or 0.0,
                        market_cap=(_f("total_mv") or 0.0) * 1e4,  # 万元 → 元
                        pe_ttm=_f("pe_ttm"),
                        ps_ttm=_f("ps_ttm"),
                        amount=(_f("amount") or 0.0) * 1e4,         # 万元 → 元
                    )
            except Exception:
                pass
        return self._ak_source().get_quote(code, market)

    def get_financials(self, code: str, market: str) -> Financials:
        if market != "A":
            return Financials(code=code)
        ts_code = self._to_ts_code(code, market)

        # ── 1. 营收 / 净利润同比（income 接口，取 8 季对比）──────────────
        revenue_growth_yoy = profit_growth_yoy = None
        try:
            inc = self.pro.income(
                ts_code=ts_code,
                fields="ts_code,end_date,total_revenue,n_income_attr_p",
                limit=10,
            )
            if inc is not None and not inc.empty:
                inc = (inc.drop_duplicates("end_date")
                          .sort_values("end_date", ascending=False)
                          .reset_index(drop=True))
                if len(inc) >= 5:
                    def _yoy(col: str) -> Optional[float]:
                        now = float(inc.at[0, col] or 0)
                        prev = float(inc.at[4, col] or 0)  # 同季去年
                        return (now - prev) / abs(prev) if prev != 0 else None
                    revenue_growth_yoy = _yoy("total_revenue")
                    profit_growth_yoy  = _yoy("n_income_attr_p")
        except Exception as e:
            print(f"[tushare] income {code}: {e}")

        # ── 2. 毛利率序列 / 研发占比 / EPS（fina_indicator 接口）─────────
        gross_margin_series: List[float] = []
        rd_ratio = eps_ttm = None
        try:
            fina = self.pro.fina_indicator(
                ts_code=ts_code,
                fields="ts_code,end_date,grossprofit_margin,rd_exp,total_revenue,eps",
                limit=8,
            )
            if fina is not None and not fina.empty:
                fina = (fina.drop_duplicates("end_date")
                            .sort_values("end_date", ascending=False)
                            .reset_index(drop=True))

                # 近 4 季毛利率，oldest→newest，转小数
                gm_vals = fina["grossprofit_margin"].dropna().head(4).astype(float).tolist()
                gross_margin_series = [g / 100.0 for g in reversed(gm_vals)]

                row0 = fina.iloc[0]
                rd = row0.get("rd_exp")
                rev = row0.get("total_revenue")
                if rd and rev and float(rev or 0) != 0:
                    rd_ratio = float(rd) / float(rev)

                # TTM EPS = 最近 4 季 EPS 之和
                eps_vals = fina["eps"].dropna().head(4).astype(float).tolist()
                if len(eps_vals) == 4:
                    eps_ttm = sum(eps_vals)
                elif eps_vals:
                    eps_ttm = eps_vals[0]
        except Exception as e:
            print(f"[tushare] fina_indicator {code}: {e}")

        # ── 3. 经营现金流（cashflow 接口）───────────────────────────────
        operating_cashflow = None
        try:
            cf = self.pro.cashflow(
                ts_code=ts_code,
                fields="ts_code,end_date,n_cashflow_act",
                limit=2,
            )
            if cf is not None and not cf.empty:
                cf = cf.sort_values("end_date", ascending=False)
                operating_cashflow = float(cf.iloc[0]["n_cashflow_act"] or 0)
        except Exception as e:
            print(f"[tushare] cashflow {code}: {e}")

        return Financials(
            code=code,
            revenue_growth_yoy=revenue_growth_yoy,
            profit_growth_yoy=profit_growth_yoy,
            gross_margin_series=gross_margin_series,
            operating_cashflow=operating_cashflow,
            rd_ratio=rd_ratio,
            eps_ttm=eps_ttm,
        )

    def get_pe_percentile(self, code: str, market: str, years: int = 3) -> Optional[float]:
        """用 Tushare daily_basic 历史数据计算当前 PE 的历史分位（0~1）。"""
        if market != "A":
            return self._ak_source().get_pe_percentile(code, market, years)
        ts_code = self._to_ts_code(code, market)
        end = dt.date.today().strftime("%Y%m%d")
        start = (dt.date.today() - dt.timedelta(days=years * 365)).strftime("%Y%m%d")
        try:
            df = self.pro.daily_basic(
                ts_code=ts_code, start_date=start, end_date=end,
                fields="trade_date,pe_ttm",
            )
            if df is None or df.empty:
                return None
            df = df.sort_values("trade_date", ascending=True)
            pe_series = pd.to_numeric(df["pe_ttm"], errors="coerce").dropna()
            pe_pos = pe_series[pe_series > 0].tolist()
            if len(pe_pos) < 20:
                return None
            current_pe = pe_pos[-1]
            pct = sum(1 for p in pe_pos if p <= current_pe) / len(pe_pos)
            return round(pct, 3)
        except Exception as e:
            print(f"[tushare] pe_percentile {code}: {e}")
            return None


# ---------------------------------------------------------------------------
# YFinance 源（HK / US，全球可用）
# ---------------------------------------------------------------------------

class YFinanceSource(DataSource):
    """Yahoo Finance：HK/US 行情，无需 token，全球可访问。"""
    name = "yfinance"

    def __init__(self):
        import yfinance as yf
        self._yf = yf
        self._tickers: dict = {}                   # sym → yf.Ticker（同进程复用）
        self._hist: dict = {}                       # sym → (datetime, DataFrame)

    @staticmethod
    def _symbol(code: str, market: str) -> str:
        """把内部代码转成 yfinance ticker。"""
        if market == "HK":
            # Yahoo Finance 去掉前导零：09992 → 9992.HK，00241 → 241.HK
            return f"{int(code)}.HK"
        if market == "A":
            # 6/9 开头 → 上交所(.SS)，其余 → 深交所(.SZ)
            return f"{code}.SS" if code[0] in ("6", "9") else f"{code}.SZ"
        return code  # US 直接用 ticker

    def _ticker(self, sym: str):
        if sym not in self._tickers:
            self._tickers[sym] = self._yf.Ticker(sym)
        return self._tickers[sym]

    def _fetch_hist(self, sym: str, days: int) -> pd.DataFrame:
        """带 5 分钟 TTL 的历史数据缓存，避免同一进程重复 HTTP 请求。"""
        cached = self._hist.get(sym)
        if cached:
            ts, df = cached
            if (dt.datetime.now() - ts).total_seconds() < 300 and len(df) >= days:
                return df
        period_days = max(int(days * 1.6), 30)
        try:
            df = self._ticker(sym).history(period=f"{period_days}d")
        except Exception as e:
            print(f"[yfinance] history {sym}: {e}")
            df = pd.DataFrame()
        self._hist[sym] = (dt.datetime.now(), df)
        return df

    def get_daily(self, code: str, market: str, days: int = 120) -> List[float]:
        sym = self._symbol(code, market)
        df = self._fetch_hist(sym, days)
        if df.empty:
            return []
        return df["Close"].astype(float).tolist()[-days:]

    def get_quote(self, code: str, market: str) -> Optional[Quote]:
        sym = self._symbol(code, market)
        # 优先复用已缓存的历史（分析时 get_daily 先调用，缓存已足够）
        cached = self._hist.get(sym)
        if cached and (dt.datetime.now() - cached[0]).total_seconds() < 300 and not cached[1].empty:
            df = cached[1]
        else:
            df = self._fetch_hist(sym, 5)
        if df.empty:
            return None
        price   = float(df["Close"].iloc[-1])
        pct_chg = 0.0
        if len(df) >= 2:
            prev    = float(df["Close"].iloc[-2])
            pct_chg = (price - prev) / prev * 100 if prev else 0.0
        volume = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0.0
        return Quote(code=code, price=price, pct_change=pct_chg, amount=volume)


# ---------------------------------------------------------------------------
# 混合源：A 股用 AKShare/Tushare，HK/US 用 yfinance
# ---------------------------------------------------------------------------

class HybridSource(DataSource):
    """A 股走 a_src，HK/US 走 yfinance。自动路由。"""
    name = "hybrid"

    def __init__(self, a_src: DataSource):
        self._a   = a_src
        self._yf  = None

    def _yf_src(self) -> YFinanceSource:
        if self._yf is None:
            self._yf = YFinanceSource()
        return self._yf

    def _route(self, market: str) -> DataSource:
        return self._a if market == "A" else self._yf_src()

    @property
    def name(self) -> str:  # type: ignore[override]
        return f"hybrid({self._a.name}+yfinance)"

    def get_daily(self, code, market, days=120):
        result = self._route(market).get_daily(code, market, days)
        # A 股 AKShare 失败时降级 yfinance
        if not result and market == "A":
            try:
                result = self._yf_src().get_daily(code, market, days)
            except Exception:
                pass
        return result

    def get_quote(self, code, market):
        result = self._route(market).get_quote(code, market)
        # A 股 AKShare 失败时降级 yfinance
        if result is None and market == "A":
            try:
                result = self._yf_src().get_quote(code, market)
            except Exception:
                pass
        return result

    def get_financials(self, code, market):
        return self._a.get_financials(code, market)

    def get_pe_percentile(self, code, market, years=3):
        return self._a.get_pe_percentile(code, market, years)


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def get_source() -> DataSource:
    """
    优先级：
      有 TUSHARE_TOKEN → HybridSource(TushareSource, YFinanceSource)
      有 yfinance      → HybridSource(AKShareSource, YFinanceSource)
      否则            → AKShareSource（降级）
    """
    from config import TUSHARE_TOKEN_ENV

    # A 股源
    token = os.environ.get(TUSHARE_TOKEN_ENV, "").strip()
    if token:
        try:
            a_src = TushareSource(token)
        except Exception as e:
            print(f"[data_source] Tushare 初始化失败，降级 AKShare：{e}")
            a_src = AKShareSource()
    else:
        a_src = AKShareSource()

    # 尝试构建混合源（需要 yfinance 已安装）
    try:
        import yfinance  # noqa: F401
        return HybridSource(a_src)
    except ImportError:
        print("[data_source] yfinance 未安装，HK/US 数据降级 AKShare。pip install yfinance")
        return a_src
