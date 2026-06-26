# -*- coding: utf-8 -*-
"""
飞书推送。webhook 从环境变量读取，绝不硬编码。
build_daily_card 为纯函数，可离线测试。
"""
from __future__ import annotations
import os, json, urllib.request
from typing import List, Dict
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
