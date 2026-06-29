# -*- coding: utf-8 -*-
"""
选股系统配置 —— 所有可调参数集中在此。
仅用于研究/学习，不构成投资建议。
"""

# ---------------- 关注列表 ----------------
# market: A=A股, HK=港股, US=美股, PRIMARY=一级市场/未上市
WATCHLIST = [
    {"name": "澜起科技",   "code": "688008", "market": "A",  "note": "半导体/内存接口芯片"},
    {"name": "澜起科技H",  "code": "06809",  "market": "HK", "note": "2026-02-09 港交所上市，发行价 HK$106.89"},
    {"name": "秦川机床",   "code": "000837", "market": "A",  "note": "机床"},
    {"name": "泡泡玛特",   "code": "09992",  "market": "HK", "note": "潮玩"},
    {"name": "阿里健康",   "code": "00241",  "market": "HK", "note": "医疗"},
    {"name": "Circle",     "code": "CRCL",   "market": "US", "note": "稳定币 USDC"},
    {"name": "智谱",       "code": "",       "market": "PRIMARY", "note": "跟踪 IPO 动态"},
    {"name": "MiniMax",    "code": "",       "market": "PRIMARY", "note": "跟踪 IPO 动态"},
    {"name": "壁仞科技",   "code": "06082",  "market": "HK", "note": "AI芯片，2026年港交所上市"},
]

# ---------------- 题材池 ----------------
TARGET_SECTORS = ["科技", "半导体", "AI", "新能源", "生物医药", "软件", "光模块", "先进封装"]

# ---------------- 第一层：基础筛选阈值（A股）----------------
SCREEN_A = {
    "market_cap_min": 50e8,      # 50 亿人民币
    "market_cap_max": 5000e8,    # 5000 亿
    "daily_amount_min": 5000e4,  # 日均成交额 5000 万元
    "revenue_growth_yoy_min": 0.30,
    "profit_growth_yoy_min": 0.35,
    "forward_pe_max": 30,
    "peg_max": 1.0,
    "ps_max": 10,
    "operating_cashflow_positive": True,
    "exclude_st": True,
    "ocf_ni_ratio_min": 0.5,
    "core_profit_ratio_min": 0.5,
}
SCREEN = SCREEN_A   # 向后兼容（screener.py 直接 import SCREEN）

# ---------------- 第一层：基础筛选阈值（港股）----------------
SCREEN_HK = {
    "market_cap_min": 20e8,      # 20 亿港元（约 18 亿人民币）
    "market_cap_max": None,
    "daily_amount_min": 1000e4,  # 1000 万港元日成交（港股流动性较弱）
    "pe_ttm_max": 80,            # 剔除极高 PE
}

# ---------------- 第一层：基础筛选阈值（美股）----------------
SCREEN_US = {
    "market_cap_min": None,      # 用固定 Universe 控制范围，不做市值下限
    "daily_amount_min": None,
    "pe_ttm_max": 200,           # 成长股 PE 可较高，宽松过滤
}

# ---------------- 第二层：隐形股票加分权重 ----------------
SCORE_WEIGHTS = {
    # 原有因子
    "ps_lt5_rev_gt100": 15,      # PS<5 且营收增速>100%
    "rd_ratio_gt15": 5,          # 研发占比 >15%
    "gross_margin_3q_up": 10,    # 毛利率连续3季提升
    "ocf_improving": 10,         # 经营现金流大幅改善（外部信号）
    "new_institution_survey": 10,# 近3月新增机构调研
    "insider_buying": 15,        # 高管/大股东增持
    "analyst_coverage_0to1": 10, # 分析师覆盖 0→1
    "industry_uptrend": 5,       # 行业景气度上升
    # 质量因子（新增）
    "roe_trend_up_3q": 10,       # ROE 连续3季提升（趋势向好）
    "roe_gt15": 8,               # ROE > 15%（盈利能力强）
    "ocf_ni_gt12": 8,            # OCF/净利润 > 1.2（利润含金量高）
    "core_profit_high": 5,       # 扣非/净利 > 90%（利润来自主业）
}

# ---------------- 降权护栏（"澜起教训"：过度定价就扣分）----------------
PENALTY = {
    # 原有护栏
    "pe_percentile_gt80": -20,   # PE 处历史 >80% 分位
    "pe_percentile_gt90": -15,   # >90% 分位再叠加（合计 -35）
    "price_1y_gt300pct": -10,    # 近一年涨幅 >300%
    # 质量风险扣分（新增）
    "ocf_ni_lt08": -15,          # OCF/净利润 < 0.8（现金流质量差，潜在利润水分）
    "core_profit_lt07": -10,     # 扣非/净利 < 70%（依赖补贴/资产出售维持利润）
    "price_1y_gt200pct": -5,     # 近一年涨幅 >200% 预警（<300% 的宽松档）
}

# ---------------- 市场分层 ----------------
MARKET_DEPTH = {
    "A":  "full",   # 题材+财务+估值+认知差+买点
    "HK": "lite",   # 行情+技术买点（财务条件 skip）
    "US": "lite",
}

# ---------------- 买点 / 风控参数 ----------------
BUY_POINT = {
    "ma_short": 20,
    "ma_long": 60,
    "buy_discount_to_ma20": 0.98,
    "stop_loss_ratio": 0.85,
    "target_pe": 30,
    "pe_percentile_max": 0.50,
}

# ---------------- 持仓 ----------------
MAX_HOLDINGS = 15
# 填入格式：{"688008": {"cost": 240.0, "shares": 100}}
HOLDINGS = {}

# ---------------- 推送 ----------------
PUSH = {
    "daily_time": "08:30",
    # 方式一：飞书自定义机器人 webhook（优先）
    "feishu_webhook_env": "FEISHU_WEBHOOK_URL",
    # 方式二：飞书应用 API（app_id + app_secret + chat_id）
    "feishu_app_id_env":     "FEISHU_APP_ID",
    "feishu_app_secret_env": "FEISHU_APP_SECRET",
    "feishu_chat_id_env":    "FEISHU_CHAT_ID",
    # newsagent 飞书群（在 .env 中填入对应群的 chat_id）
    "newsagent_chat_id_env": "NEWSAGENT_CHAT_ID",
}

# ---------------- 数据源 ----------------
TUSHARE_TOKEN_ENV = "TUSHARE_TOKEN"
