#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书双向交互层 —— 接收飞书群消息，执行股票指令，回复结果。

原理
----
通过飞书应用 WebSocket 长连接（无需公网服务器）接收消息事件。
需安装：pip install lark-oapi

⚠ 注意
------
如果 openclaw 也在用同一个 app_id 连接飞书，两个进程会竞争同一事件流
（飞书会将消息随机分发给其中一个客户端）。
建议方案：
  方案 A：只在需要股票指令时运行本脚本，暂停 openclaw；
  方案 B：创建一个专属的"股票助手"飞书群，本脚本监听该群。

用法
----
  python3 feishu_handler.py          # 正常运行（保持前台）
  python3 feishu_handler.py --once   # 单次测试（先检查环境，立刻退出）

指令列表（在飞书群中发送）
-------------------------
  买入 <代码> <成本价> <股数>      买入 688008 260.0 100
  卖出 <代码>                       卖出 688008
  持仓                              列出所有持仓和盈亏
  加股 <代码> <名称> [市场]         加股 600036 招商银行 A
  减股 <代码>                       减股 688008
  关注列表                          查看当前所有关注股
  查 <代码>                         查 688008 → 当前价/买点/止损
  日报                              立即触发一次完整选股日报
  帮助                              显示本列表

仅供研究学习，不构成投资建议。
"""
from __future__ import annotations
import os, sys, json, datetime as dt
from typing import Optional

# ── 环境变量 ──────────────────────────────────────────────────────────────────
APP_ID     = os.environ.get("FEISHU_APP_ID", "").strip()
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "").strip()
CHAT_ID    = os.environ.get("FEISHU_CHAT_ID", "").strip()

HELP_TEXT = """📋 股票助手指令手册

【持仓管理】
  买入 <代码> <成本价> <股数>
    例：买入 688008 260.0 100
  卖出 <代码>
    例：卖出 688008
  持仓  → 列出全部持仓和盈亏

【关注列表】
  加股 <代码> <名称> [市场A/HK/US]
    例：加股 600036 招商银行 A
  减股 <代码>
    例：减股 688008
  关注列表  → 查看当前关注股

【即时查询】
  查 <代码>   → 当前价/买点/止损
    例：查 688008
  日报   → 立即生成选股日报
  帮助   → 显示本列表

⚠️ 仅供研究学习，不构成投资建议。"""


# ── 延迟导入（避免 import 阶段报错影响主流程） ───────────────────────────────

def _get_lark():
    try:
        import lark_oapi as lark
        return lark
    except ImportError:
        print("❌ lark-oapi 未安装，请运行：pip install lark-oapi")
        sys.exit(1)


# ── 回复工具 ──────────────────────────────────────────────────────────────────

def _reply(client, receive_id: str, text: str):
    """向指定 receive_id（chat_id 或 user_id）回复文本消息。"""
    lark = _get_lark()
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest, CreateMessageRequestBody,
    )
    req = (CreateMessageRequest.builder()
           .receive_id_type("chat_id")
           .request_body(
               CreateMessageRequestBody.builder()
               .receive_id(receive_id)
               .msg_type("text")
               .content(json.dumps({"text": text}))
               .build()
           )
           .build())
    resp = client.im.v1.message.create(req)
    if not resp.success():
        print(f"[feishu_handler] 回复失败: code={resp.code} msg={resp.msg}")


# ── 指令解析 & 执行 ───────────────────────────────────────────────────────────

def _handle_text(text: str, client, chat_id: str) -> Optional[str]:
    """
    解析文本指令。返回回复字符串；None 表示不是股票指令，忽略。
    """
    from holdings_store import (
        load_holdings, add_holding, remove_holding,
        add_to_watchlist, remove_from_watchlist, load_dynamic_watchlist,
    )
    from config import WATCHLIST
    from data_source import get_source
    from buy_point import calculate_buy_point

    parts = text.strip().split()
    if not parts:
        return None
    cmd = parts[0]

    # ── 帮助 ──────────────────────────────────────────────────────────────────
    if cmd in ("帮助", "help", "？", "?"):
        return HELP_TEXT

    # ── 买入 <代码> <成本价> <股数> ──────────────────────────────────────────
    if cmd == "买入":
        if len(parts) < 4:
            return "格式错误：买入 <代码> <成本价> <股数>\n例：买入 688008 260.0 100"
        code = parts[1]
        try:
            cost   = float(parts[2])
            shares = int(parts[3])
        except ValueError:
            return "成本价/股数格式错误，请输入数字"
        # 尝试在 WATCHLIST 中找名称
        wl_item = next((w for w in WATCHLIST if w["code"] == code), None)
        name = wl_item["name"] if wl_item else code
        return add_holding(code, name, cost, shares)

    # ── 卖出 <代码> ───────────────────────────────────────────────────────────
    if cmd == "卖出":
        if len(parts) < 2:
            return "格式错误：卖出 <代码>\n例：卖出 688008"
        return remove_holding(parts[1])

    # ── 持仓 ─────────────────────────────────────────────────────────────────
    if cmd == "持仓":
        holdings = load_holdings()
        if not holdings:
            return "📭 当前无持仓记录"
        try:
            src = get_source()
        except Exception:
            src = None

        lines = [f"📈 持仓列表（{dt.date.today()}）\n"]
        total_cost = total_val = 0.0
        for code, pos in holdings.items():
            name  = pos.get("name", code)
            cost  = pos.get("cost") or 0.0
            shs   = pos.get("shares") or 0
            price_str = pnl_str = "N/A"
            try:
                if src:
                    wl_item = next((w for w in WATCHLIST if w["code"] == code), {})
                    market  = wl_item.get("market", "A")
                    q = src.get_quote(code, market)
                    if q and q.price:
                        price_str = f"¥{q.price:.2f}"
                        pnl = (q.price - cost) / cost * 100 if cost else 0
                        pnl_str = f"{pnl:+.1f}%"
                        total_cost += cost * shs
                        total_val  += q.price * shs
            except Exception:
                pass
            lines.append(f"  {name}({code})\n  成本 ¥{cost}  现价 {price_str}  {shs}股  盈亏 {pnl_str}")

        if total_cost > 0:
            total_pnl = (total_val - total_cost) / total_cost * 100
            lines.append(f"\n总盈亏：{total_pnl:+.1f}%")
        lines.append("\n⚠️ 仅供研究，非投资建议")
        return "\n".join(lines)

    # ── 加股 <代码> <名称> [市场] ─────────────────────────────────────────────
    if cmd == "加股":
        if len(parts) < 3:
            return "格式错误：加股 <代码> <名称> [市场A/HK/US]\n例：加股 600036 招商银行 A"
        code   = parts[1]
        name   = parts[2]
        market = parts[3].upper() if len(parts) >= 4 else "A"
        if market not in ("A", "HK", "US"):
            return f"市场代码错误：{market}（支持 A / HK / US）"
        return add_to_watchlist(code, name, market)

    # ── 减股 <代码> ───────────────────────────────────────────────────────────
    if cmd == "减股":
        if len(parts) < 2:
            return "格式错误：减股 <代码>\n例：减股 688008"
        return remove_from_watchlist(parts[1])

    # ── 关注列表 ──────────────────────────────────────────────────────────────
    if cmd in ("关注列表", "关注"):
        base = [w for w in WATCHLIST if w.get("code")]
        dyn  = load_dynamic_watchlist()
        lines = [f"👁 关注列表（{len(base)+len(dyn)} 只）\n"]
        lines.append("【基础列表】")
        for w in base:
            lines.append(f"  {w['name']}({w['code']}) [{w['market']}] {w.get('note','')}")
        if dyn:
            lines.append("\n【飞书动态加入】")
            for w in dyn:
                lines.append(f"  {w['name']}({w['code']}) [{w['market']}] {w.get('note','')}")
        return "\n".join(lines)

    # ── 查 <代码> ─────────────────────────────────────────────────────────────
    if cmd == "查":
        if len(parts) < 2:
            return "格式错误：查 <代码>\n例：查 688008"
        code = parts[1]
        wl_item = next((w for w in WATCHLIST if w["code"] == code), {})
        market  = wl_item.get("market", "A")
        name    = wl_item.get("name", code)
        try:
            src    = get_source()
            prices = src.get_daily(code, market, 130)
            q      = src.get_quote(code, market)
            if not prices or q is None:
                return f"⚠️ {code} 无行情数据"
            bp = calculate_buy_point(prices)
            lines = [
                f"📊 {name}({code}) [{market}]",
                f"  现价：¥{q.price:.3f}",
                f"  买点：¥{bp.get('buy_point', 'N/A')}",
                f"  止损：¥{bp.get('stop_loss', 'N/A')}",
                f"  目标：{'¥'+str(bp.get('target_price')) if bp.get('target_price') else 'N/A'}",
                f"  MA20：¥{bp.get('ma20', 'N/A')}",
                f"  趋势：{'↑ 上升' if bp.get('trend_up') else '↓ 下降' if bp.get('trend_up') is False else 'N/A'}",
                f"\n⚠️ 仅供研究，非投资建议",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"⚠️ 查询失败：{e}"

    # ── 日报 ─────────────────────────────────────────────────────────────────
    if cmd == "日报":
        try:
            import run_daily
            run_daily.run(dry_run=False)
            return "✅ 日报已触发，请查看推送"
        except Exception as e:
            return f"⚠️ 日报触发失败：{e}"

    # 不是已知指令 → 忽略
    return None


# ── WebSocket 事件处理 ────────────────────────────────────────────────────────

def _make_handler(client):
    def on_message(data) -> None:
        try:
            msg = data.event.message
            # 只处理 text 类型消息
            if msg.message_type != "text":
                return
            chat_id     = msg.chat_id
            raw_content = msg.content or "{}"
            text        = json.loads(raw_content).get("text", "").strip()
            if not text:
                return
            print(f"[feishu_handler] 收到消息 chat={chat_id}: {text!r}")
            reply = _handle_text(text, client, chat_id)
            if reply:
                _reply(client, chat_id, reply)
        except Exception as e:
            print(f"[feishu_handler] 处理消息出错: {e}")
    return on_message


# ── 主入口 ───────────────────────────────────────────────────────────────────

def main(once: bool = False):
    if not APP_ID or not APP_SECRET:
        print("❌ 未设置 FEISHU_APP_ID / FEISHU_APP_SECRET，请检查 .env 文件")
        sys.exit(1)

    lark = _get_lark()

    # 构建 HTTP 客户端（用于主动发消息）
    client = (lark.Client.builder()
              .app_id(APP_ID)
              .app_secret(APP_SECRET)
              .log_level(lark.LogLevel.WARNING)
              .build())

    if once:
        print("[feishu_handler] --once 测试模式：环境检查通过，不建立长连接")
        print(f"  APP_ID:    {APP_ID[:8]}...")
        print(f"  APP_SECRET: ****")
        print(f"  CHAT_ID:   {CHAT_ID or '未设置'}")
        _reply(client, CHAT_ID, "🤖 股票助手已启动（测试 ping），发送「帮助」查看指令")
        return

    from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

    ws_client = (lark.ws.Client(
        APP_ID, APP_SECRET,
        event_handler=(
            lark.EventDispatcherHandler.builder("", "")
            .register(P2ImMessageReceiveV1, _make_handler(client))
            .build()
        ),
        log_level=lark.LogLevel.WARNING,
    ))

    print("[feishu_handler] 🚀 连接飞书 WebSocket 长连接...")
    print("  发送「帮助」到飞书群可查看所有指令")
    print("  按 Ctrl+C 停止")
    ws_client.start()


if __name__ == "__main__":
    main(once="--once" in sys.argv)
