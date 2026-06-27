# -*- coding: utf-8 -*-
"""
推送层：飞书 webhook + Obsidian Markdown + Notion Database。
所有 token/webhook 从环境变量读取，绝不硬编码。

环境变量：
  FEISHU_WEBHOOK_URL   飞书机器人 webhook
  NOTION_TOKEN         Notion Integration token
  NOTION_DATABASE_ID   写入目标 Database 的 ID
"""
from __future__ import annotations
import os, json, urllib.request
import datetime as dt
from typing import List, Dict, Optional
from config import PUSH


def build_daily_text(date: str, candidates: List[Dict], holdings: List[Dict]) -> str:
    """生成纯文本日报（飞书 text 消息体）。研究用途，非投资建议。"""
    lines = [f"📊 选股日报 - {date}", ""]
    lines.append(f"🎯 候选（{len(candidates)} 只）")
    for i, c in enumerate(candidates, 1):
        bp = c.get("buy", {})
        lines.append(
            f"{i}. {c.get('name','')} {c.get('code','')} | 分 {c.get('score',0)}"
            f" | 现价 {bp.get('current','-')} | 建议买点 {bp.get('buy_point','-')}"
            f" | 止损 {bp.get('stop_loss','-')}"
        )
        if c.get("hits"):
            lines.append("   触发: " + "、".join(c["hits"]))
    lines.append("")
    lines.append(f"📈 持仓跟踪（上限 {len(holdings)} 只）")
    for h in holdings:
        lines.append(f"- {h.get('name','')} {h.get('code','')} | 成本 {h.get('cost','-')} "
                     f"| 现价 {h.get('price','-')} | {h.get('pnl_pct','-')}")
    lines.append("")
    lines.append("⚠️ 仅供研究学习，不构成投资建议。")
    return "\n".join(lines)


def send_feishu(text: str) -> Dict:
    url = os.environ.get(PUSH["feishu_webhook_env"], "").strip()
    if not url:
        return {"sent": False, "reason": f"未配置 {PUSH['feishu_webhook_env']}"}
    body = json.dumps({"msg_type": "text", "content": {"text": text}}).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return {"sent": True, "resp": r.read().decode("utf-8")}
    except Exception as e:
        return {"sent": False, "reason": repr(e)}


# ---------------------------------------------------------------------------
# Obsidian：输出 Markdown 文件（通过 git 同步到 vault）
# ---------------------------------------------------------------------------

def build_obsidian_daily_md(date: str, candidates: List[Dict],
                             holdings: List[Dict]) -> str:
    """生成适合存入 Obsidian vault 的 Markdown 日报。"""
    lines = [
        f"# 选股日报 {date}",
        "",
        "> ⚠️ 仅供研究学习，不构成投资建议。",
        f"> 标签: #stock/daily #可公开",
        "",
        f"## 候选（{len(candidates)} 只）",
        "",
    ]
    for i, c in enumerate(candidates, 1):
        bp = c.get("buy", {})
        lines += [
            f"### {i}. {c.get('name','')} `{c.get('code','')}`",
            f"- 综合得分：**{c.get('score', 0)}**",
            f"- 现价：{bp.get('current', '-')}  建议买点：{bp.get('buy_point', '-')}  止损：{bp.get('stop_loss', '-')}",
            f"- 目标价：{bp.get('target_price', '-')}  风险收益比：{bp.get('risk_reward', '-')}",
            f"- 触发：{'、'.join(c['hits']) if c.get('hits') else '—'}",
            "",
        ]
    if holdings:
        lines += ["## 持仓跟踪", ""]
        for h in holdings:
            lines.append(f"- **{h.get('code','')}** 成本 {h.get('cost','-')}  现价 {h.get('price','-')}")
    return "\n".join(lines)


def save_obsidian_daily(date: str, candidates: List[Dict],
                        holdings: List[Dict],
                        vault_logs_dir: str = "logs") -> str:
    """
    把日报写入本地路径（供 git 同步到 Obsidian vault）。
    vault_logs_dir 建议指向 vault 内的 logs/ 目录或 git repo 的 logs/ 目录。
    返回写入的文件路径。
    """
    import pathlib
    path = pathlib.Path(vault_logs_dir) / f"{date}-stock-daily.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_obsidian_daily_md(date, candidates, holdings),
                    encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Notion：写入选股看板 Database
# ---------------------------------------------------------------------------

def _notion_request(method: str, endpoint: str,
                    token: str, body: Optional[Dict] = None) -> Dict:
    url = f"https://api.notion.com/v1/{endpoint}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return {"ok": True, "data": json.loads(r.read())}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "reason": e.read().decode()}
    except Exception as e:
        return {"ok": False, "reason": repr(e)}


def push_to_notion(candidates: List[Dict], date: str) -> Dict:
    """
    把选股候选写入 Notion Database（选股看板）。
    需要环境变量 NOTION_TOKEN 和 NOTION_DATABASE_ID。
    每只股票对应 Database 中的一条记录。
    """
    token = os.environ.get("NOTION_TOKEN", "").strip()
    db_id = os.environ.get("NOTION_DATABASE_ID", "").strip()
    if not token or not db_id:
        return {"sent": False, "reason": "未配置 NOTION_TOKEN 或 NOTION_DATABASE_ID"}

    results = []
    for c in candidates:
        bp = c.get("buy", {})
        props = {
            "股票名称": {"title": [{"text": {"content": c.get("name", "")}}]},
            "代码":     {"rich_text": [{"text": {"content": c.get("code", "")}}]},
            "市场":     {"select": {"name": c.get("market", "A")}},
            "综合得分": {"number": c.get("score", 0)},
            "建议买点": {"number": bp.get("buy_point") or 0},
            "止损位":   {"number": bp.get("stop_loss") or 0},
            "目标价":   {"number": bp.get("target_price") or 0},
            "触发信号": {"multi_select": [{"name": h} for h in (c.get("hits") or [])[:5]]},
            "更新日期": {"date": {"start": date}},
            "状态":     {"select": {"name": "候选"}},
        }
        body = {"parent": {"database_id": db_id}, "properties": props}
        r = _notion_request("POST", "pages", token, body)
        results.append({"code": c.get("code"), "ok": r.get("ok")})

    ok_count = sum(1 for r in results if r["ok"])
    return {"sent": True, "ok": ok_count, "total": len(results), "detail": results}
