#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书交互卡片构建器 —— 选股结果 + 「加入关注」按钮。

用法：
  from feishu_card import build_screen_card
  card = build_screen_card("A", top_results, n_scanned=40, label="半导体")
  # 再通过 push.send_feishu_card(card) 发送
"""
from __future__ import annotations
from typing import List, Dict
import datetime as dt


_MKT = {
    "A":  {"flag": "🇨🇳", "label": "A股",  "cur": "¥",    "tpl": "blue"},
    "HK": {"flag": "🇭🇰", "label": "港股",  "cur": "HK$",  "tpl": "wathet"},
    "US": {"flag": "🇺🇸", "label": "美股",  "cur": "$",    "tpl": "green"},
}


def build_screen_card(market: str, results: List[Dict],
                      n_scanned: int = 0, label: str = "") -> Dict:
    """
    将 screen_a/hk/us() 返回的 top 列表转为飞书交互卡片 JSON。

    每只股票：
      - 左侧：名称、价格、得分、信号标签
      - 右侧：「⭐ 加入关注」按钮（value 携带 code/name/market）
    按钮点击后由 feishu_handler.py 的卡片回调处理。
    """
    cfg = _MKT.get(market.upper(), _MKT["A"])
    cur = cfg["cur"]
    today = dt.date.today().strftime("%Y-%m-%d")
    title = f"{cfg['flag']} {cfg['label']}选股  {today}"
    if label:
        title += f"  · {label}"

    n_passed = sum(1 for r in results if r.get("basic_pass"))
    summary = f"扫描 **{n_scanned}** 只  →  通过基础筛选 **{n_passed}** 只"

    elements: List[Dict] = [
        {"tag": "markdown", "content": summary},
        {"tag": "hr"},
    ]

    for r in results:
        status = "✅" if r["basic_pass"] else "⬜"
        pe_s   = f"  PE={r['pe']:.0f}" if r.get("pe") else ""
        pct_s  = f"  {r['pct']:+.1f}%" if r.get("pct") is not None else ""
        y1_s   = (f"  1年{r['price_1y_pct']*100:+.0f}%"
                  if r.get("price_1y_pct") is not None else "")

        lines = [
            f"**{r['rank']}. {status} {r['name']}({r['code']})**"
            f"  {cur}{r['price']:.2f}{pct_s}{pe_s}{y1_s}"
            f"  得分**{r['score']:+d}**"
        ]
        if r.get("description"):
            desc = r["description"]
            if len(desc) > 110:
                desc = desc[:107] + "..."
            lines.append(f"📝 {desc}")
        if r.get("hits"):
            lines.append("✦ " + " | ".join(r["hits"]))
        if r.get("basic_reasons"):
            lines.append("✗ " + " | ".join(r["basic_reasons"]))

        bp = r.get("buy") or {}
        if bp and not bp.get("error"):
            trend = ("↑" if bp.get("trend_up") else
                     "↓" if bp.get("trend_up") is False else "—")
            pts = []
            if bp.get("buy_point"): pts.append(f"买点{cur}{bp['buy_point']:.2f}")
            if bp.get("stop_loss"): pts.append(f"止损{cur}{bp['stop_loss']:.2f}")
            if pts:
                lines.append(f"趋势{trend}  " + " | ".join(pts))

        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(lines)},
        })
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "⭐ 加入关注"},
                    "type": "primary" if r["basic_pass"] else "default",
                    "value": {
                        "action": "watch",
                        "code":   r["code"],
                        "name":   r["name"],
                        "market": market.upper(),
                    },
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "📰 公司动态"},
                    "type": "default",
                    "value": {
                        "action": "news",
                        "code":   r["code"],
                        "name":   r["name"],
                        "market": market.upper(),
                    },
                },
            ],
        })
        elements.append({"tag": "hr"})

    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text",
                      "content": "⚠️ 仅供研究学习，不构成投资建议"}],
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": cfg["tpl"],
        },
        "elements": elements,
    }


def build_daily_card(
    date: str,
    candidates: List[Dict],
    holdings: List[Dict],
    sentiment: Dict = None,
    suggestions: List[str] = None,
) -> Dict:
    """将 run_daily 的选股结果构建为飞书卡片。

    新版结构：持仓盈亏快照 → 今日操作建议 → 候选选股 → 市场情绪。
    sentiment: {"n_up": x, "n_down": y, "avg_pct": z, "n_total": n}
    suggestions: ["【股票】信号描述", ...]
    """

    def _row(cells, weights):
        return {
            "tag": "column_set",
            "flex_mode": "none",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": w,
                    "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": txt}}],
                }
                for txt, w in zip(cells, weights)
            ],
        }

    elements: List[Dict] = []

    # ── 持仓盈亏快照 ──────────────────────────────────────────────────────
    elements.append({"tag": "markdown", "content": "**📈 持仓盈亏快照**"})
    if holdings:
        H_W = [4, 2, 2, 2, 3]
        elements.append(_row(
            ["**股票**", "**成本**", "**现价**", "**今日**", "**盈亏 / 信号**"],
            H_W,
        ))
        elements.append({"tag": "hr"})
        for h in holdings:
            cost    = str(h["cost"])  if h.get("cost")  else "-"
            price   = str(h["price"]) if h.get("price") else "-"
            pnl     = h.get("pnl_pct") or "-"
            today_p = h.get("today_pct")
            signal  = h.get("signal") or ""
            today_s = f"{today_p:+.2f}%" if today_p is not None else "-"
            pnl_signal = pnl + (f"\n{signal}" if signal else "")
            elements.append(_row(
                [f"**{h['name']}**\n{h['code']}", cost, price, today_s, pnl_signal],
                H_W,
            ))
    else:
        elements.append({"tag": "markdown", "content": "当前无持仓"})
    elements.append({"tag": "hr"})

    # ── 今日操作建议 ──────────────────────────────────────────────────────
    if suggestions:
        sug_content = "**⚡ 今日操作建议**\n\n" + "\n".join(f"▸ {s}" for s in suggestions)
        elements.append({"tag": "markdown", "content": sug_content})
        elements.append({"tag": "hr"})

    # ── 候选选股 ──────────────────────────────────────────────────────────
    C_W = [1, 5, 4, 1]
    elements.append({"tag": "markdown", "content": f"**🎯 候选选股（{len(candidates)} 只）**"})
    elements.append(_row(["**序**", "**名称（代码）市场**", "**现价 / 买点 / 止损**", "**分**"], C_W))
    elements.append({"tag": "hr"})

    for i, c in enumerate(candidates, 1):
        bp  = c.get("buy") or {}
        cur = bp.get("current", "-")
        bpt = bp.get("buy_point", "-")
        stp = bp.get("stop_loss", "-")
        if isinstance(cur, float): cur = f"{cur:.2f}"
        if isinstance(bpt, float): bpt = f"{bpt:.2f}"
        if isinstance(stp, float): stp = f"{stp:.2f}"
        flag  = "✅" if c.get("basic_pass") else "⬜"
        score = c.get("score", 0)
        pe_s  = f"  PE {c['pe_ttm']:.0f}x" if c.get("pe_ttm") else ""
        pct_s = f"  {c['today_pct']:+.1f}%" if c.get("today_pct") is not None else ""
        elements.append(_row([
            str(i),
            f"{flag} **{c['name']}**\n{c['code']}  [{c.get('market', '-')}]{pe_s}",
            f"现价 **{cur}**{pct_s}\n买点 {bpt}  止损 {stp}",
            f"**{score:+d}**",
        ], C_W))

    # 触发信号
    elements.append({"tag": "hr"})
    _SKIP = {"lite:仅技术面"}
    sig_lines = []
    for c in candidates:
        hits = [h for h in (c.get("hits") or []) if h not in _SKIP]
        if hits:
            sig_lines.append(f"**{c['name']}**：" + " · ".join(hits))
    if sig_lines:
        elements.append({
            "tag": "markdown",
            "content": "**✦ 触发信号**\n\n" + "\n".join(sig_lines),
        })
        elements.append({"tag": "hr"})

    # ── 市场情绪 ──────────────────────────────────────────────────────────
    if sentiment and sentiment.get("n_total", 0) > 0:
        n_up   = sentiment.get("n_up", 0)
        n_down = sentiment.get("n_down", 0)
        n_tot  = sentiment.get("n_total", 0)
        avg_p  = sentiment.get("avg_pct")
        avg_s  = f"{avg_p:+.2f}%" if avg_p is not None else "N/A"
        bull_pct = n_up / n_tot * 100 if n_tot else 0
        mood = "偏多 📈" if bull_pct >= 60 else ("偏空 📉" if bull_pct <= 40 else "中性 ⟷")
        elements.append({"tag": "markdown", "content": (
            f"**🌡 市场情绪（关注股 {n_tot} 只）**\n\n"
            f"涨 **{n_up}**只  跌 **{n_down}**只  平均 {avg_s}  "
            f"多空比 {bull_pct:.0f}%  → {mood}"
        )})
        elements.append({"tag": "hr"})

    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": "⚠️ 仅供研究学习，不构成投资建议"}],
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📊 选股日报 · {date}"},
            "template": "blue",
        },
        "elements": elements,
    }


def build_news_card(name: str, code: str, market: str, articles: list) -> Dict:
    """将搜索结果构建为飞书新闻卡片。"""
    mkt_cfg = _MKT.get(market.upper(), {"flag": "🌐", "label": market, "tpl": "grey"})
    import datetime as _dt
    today = _dt.date.today().strftime("%Y-%m-%d")

    elements: list = []

    if not articles:
        elements.append({
            "tag": "markdown",
            "content": "未找到近期相关新闻，请稍后重试。",
        })
    else:
        for a in articles:
            title  = a.get("title", "（无标题）")
            source = a.get("source", "")
            url    = a.get("url", "")
            date   = (a.get("date") or "")[:10]
            body   = (a.get("body") or "")[:120]

            meta = " · ".join(filter(None, [date, source]))
            content = f"**{title}**"
            if meta:
                content += f"\n{meta}"
            if body:
                content += f"\n{body}..."
            if url:
                content += f"\n[阅读全文]({url})"

            elements.append({"tag": "markdown", "content": content})
            elements.append({"tag": "hr"})

    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text",
                      "content": "⚠️ 内容来自网络搜索，仅供参考，请自行核实"}],
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text",
                      "content": f"{mkt_cfg['flag']} {name}（{code}）公司动态  {today}"},
            "template": mkt_cfg["tpl"],
        },
        "elements": elements,
    }


def build_watchlist_confirm_card(code: str, name: str, market: str) -> Dict:
    """点击「加入关注」后发回的确认卡片。"""
    mkt_label = _MKT.get(market, {}).get("label", market)
    return {
        "config": {"wide_screen_mode": False},
        "header": {
            "title": {"tag": "plain_text", "content": "✅ 已加入关注列表"},
            "template": "green",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{name}**（{code}）[{mkt_label}] 已加入关注列表\n\n"
                        f"发送 `查 {code}` 可随时查询买点和行情\n"
                        f"发送 `减股 {code}` 可从关注列表移除"
                    ),
                },
            },
            {
                "tag": "note",
                "elements": [{"tag": "plain_text",
                              "content": "⚠️ 仅供研究学习，不构成投资建议"}],
            },
        ],
    }
