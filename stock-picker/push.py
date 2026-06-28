# -*- coding: utf-8 -*-
"""
飞书推送。所有凭证从环境变量读取，绝不硬编码。
支持两种方式（优先级：webhook > app API）：
  方式一：FEISHU_WEBHOOK_URL（自定义机器人）
  方式二：FEISHU_APP_ID + FEISHU_APP_SECRET + FEISHU_CHAT_ID（飞书应用）
"""
from __future__ import annotations
import os, json, urllib.request
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


def _http_post(url: str, payload: dict, headers: dict) -> Dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return {"ok": True, "resp": r.read().decode("utf-8")}
    except Exception as e:
        return {"ok": False, "reason": repr(e)}


def _get_tenant_token(app_id: str, app_secret: str) -> Optional[str]:
    r = _http_post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
        {"Content-Type": "application/json"},
    )
    if not r["ok"]:
        return None
    data = json.loads(r["resp"])
    return data.get("tenant_access_token")


def _send_via_app(text: str, app_id: str, app_secret: str, chat_id: str) -> Dict:
    token = _get_tenant_token(app_id, app_secret)
    if not token:
        return {"sent": False, "reason": "获取 tenant_access_token 失败"}
    r = _http_post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        {"receive_id": chat_id, "msg_type": "text",
         "content": json.dumps({"text": text})},
        {"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    return {"sent": r["ok"], **({"resp": r["resp"]} if r["ok"] else {"reason": r["reason"]})}


def send_feishu(text: str) -> Dict:
    # 方式一：webhook
    url = os.environ.get(PUSH["feishu_webhook_env"], "").strip()
    if url:
        r = _http_post(url, {"msg_type": "text", "content": {"text": text}},
                       {"Content-Type": "application/json"})
        return {"sent": r["ok"], **({"resp": r["resp"]} if r["ok"] else {"reason": r["reason"]})}

    # 方式二：app API
    app_id     = os.environ.get(PUSH["feishu_app_id_env"], "").strip()
    app_secret = os.environ.get(PUSH["feishu_app_secret_env"], "").strip()
    chat_id    = os.environ.get(PUSH["feishu_chat_id_env"], "").strip()
    if app_id and app_secret and chat_id:
        return _send_via_app(text, app_id, app_secret, chat_id)

    return {"sent": False, "reason": "未配置飞书推送（FEISHU_WEBHOOK_URL 或 FEISHU_APP_ID/SECRET/CHAT_ID）"}
