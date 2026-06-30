#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
联网新闻搜索模块 —— 基于 DuckDuckGo，无需 API Key。
支持 A股 / 港股 / 美股，自动匹配搜索语言和关键词。
"""
from __future__ import annotations
from typing import List, Dict, Optional
import datetime as dt


def search_company_news(name: str, code: str, market: str = "A",
                        max_results: int = 6) -> List[Dict]:
    """
    搜索公司近期新闻。返回文章列表，每条包含 title/date/source/url/body。
    失败时返回空列表。
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return []

    if market in ("A", "HK"):
        query = f"{name} {code} 公告 财报 新闻 最新"
        region = "cn-zh"
    else:
        query = f"{name} {code} stock news earnings announcement"
        region = "us-en"

    try:
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=max_results,
                                     region=region, safesearch="off"))
        return results
    except Exception as e:
        print(f"[news_search] 搜索失败: {e}")
        return []


def search_company_profile(name: str, code: str, market: str = "A") -> Optional[str]:
    """
    搜索公司简介（主营业务）。返回一段文本，失败返回 None。
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return None

    if market in ("A", "HK"):
        query = f"{name} 公司简介 主营业务"
        region = "cn-zh"
    else:
        query = f"{name} company overview business description"
        region = "us-en"

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3, region=region))
        if results:
            return results[0].get("body", "")[:300]
    except Exception:
        pass
    return None


def build_news_reply(name: str, code: str, market: str,
                     articles: List[Dict]) -> str:
    """将搜索结果格式化为飞书文本消息。"""
    header = f"📰 {name}（{code}）[{market}] 近期动态\n"
    if not articles:
        return header + "\n未找到近期相关新闻。\n⚠️ 仅供参考，请自行核实"

    today = dt.date.today()
    lines = [header]
    for i, a in enumerate(articles, 1):
        title  = a.get("title", "（无标题）")
        source = a.get("source", "")
        url    = a.get("url", "")
        raw_date = a.get("date", "")
        date_str = raw_date[:10] if raw_date else ""

        lines.append(f"{i}. {title}")
        meta = " · ".join(filter(None, [date_str, source]))
        if meta:
            lines.append(f"   {meta}")
        if url:
            lines.append(f"   {url}")
        lines.append("")

    lines.append("⚠️ 以上内容来自网络搜索，仅供参考，请自行核实")
    return "\n".join(lines)
