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

# ── 加载 .env ─────────────────────────────────────────────────────────────────
def _load_dotenv():
    _dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(_dir, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

_load_dotenv()

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

【选股扫描】
  选股          → A股全市场（交互卡片）
  选股 HK       → 港股扫描
  选股 US       → 美股扫描
  选股 A 半导体  → A股行业过滤

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

    # 去掉飞书 @mention 占位符（如 @_user_1）
    import re as _re
    clean = _re.sub(r'@_\S+', '', text).strip()
    parts = clean.split()
    if not parts:
        return None
    cmd = parts[0]

    # 兼容不带空格：选股US / 选股HK / 选股A → 选股 US / HK / A
    if cmd.startswith("选股") and len(cmd) > 2:
        parts = ["选股", cmd[2:]] + parts[1:]
        cmd = "选股"

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

    # ── 选股 [A|HK|US|ALL] [行业] ────────────────────────────────────────────
    if cmd == "选股":
        from market_screener import run_market_screen
        from feishu_card import build_screen_card
        from push import send_feishu_card, notify_newsagent

        MARKETS = {"A", "HK", "US", "ALL", "全部"}
        market = "A"
        sector_kw = ""
        for p in parts[1:]:
            if p.upper() in MARKETS:
                market = "ALL" if p == "全部" else p.upper()
            elif not p.startswith("-"):
                sector_kw = p

        _reply(client, chat_id, f"⏳ 正在扫描 {market} 市场，请稍候（约 30~60 秒）...")

        text, results, n_scanned = run_market_screen(
            market=market, sector_kw=sector_kw, top_n=10, structured=True
        )

        # 单市场发送交互卡片；ALL 降级为文本
        card_sent = False
        if results and market not in ("ALL", "全部"):
            try:
                card = build_screen_card(market, results, n_scanned, sector_kw)
                r = send_feishu_card(card, chat_id)
                card_sent = r.get("sent", False)
            except Exception as e:
                print(f"[feishu_handler] 卡片发送失败: {e}")

        if not card_sent:
            _reply(client, chat_id, text)

        # 通知 newsagent：通过基础筛选的公司
        passed_names = [r["name"] for r in results if r.get("basic_pass")][:8]
        if passed_names:
            notify_newsagent(passed_names)

        return None  # 已通过 _reply/_card 回复，on_message 不需再 reply

    # 不是已知指令 → 忽略
    return None


# ── WebSocket 事件处理 ────────────────────────────────────────────────────────

def _make_handler(client):
    from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
    def on_message(data: P2ImMessageReceiveV1) -> None:
        try:
            msg = data.event.message
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


def _make_card_handler(client):
    """
    卡片按钮回调处理器。飞书在用户点击卡片按钮后，通过 WebSocket 推送
    card.action.trigger 事件，这里解析 value.action 并执行相应操作。
    """
    def on_card_action(data) -> None:
        try:
            # data.event 可能是 dict 或对象，统一用 getattr/get 读取
            ev = data.event if hasattr(data, "event") else {}
            if isinstance(ev, dict):
                action_val = ev.get("action", {}).get("value", {})
                ctx        = ev.get("context", {})
                chat_id    = ctx.get("open_chat_id", CHAT_ID)
            else:
                av_raw  = getattr(getattr(ev, "action", None), "value", None)
                action_val = av_raw if isinstance(av_raw, dict) else {}
                ctx_raw = getattr(ev, "context", None)
                chat_id = (getattr(ctx_raw, "open_chat_id", None) or CHAT_ID)

            action = action_val.get("action", "") if isinstance(action_val, dict) else ""
            print(f"[card_action] action={action!r} val={action_val}")

            if action == "watch":
                code   = action_val.get("code", "")
                name   = action_val.get("name", code)
                market = action_val.get("market", "A")

                from holdings_store import add_to_watchlist
                result = add_to_watchlist(code, name, market)
                print(f"[card_action] {result}")

                # 发送确认卡片
                from feishu_card import build_watchlist_confirm_card
                from push import send_feishu_card, notify_newsagent
                confirm = build_watchlist_confirm_card(code, name, market)
                r = send_feishu_card(confirm, chat_id)
                if not r.get("sent"):
                    _reply(client, chat_id, f"✅ {result}")

                # 通知 newsagent 搜索该公司
                notify_newsagent([name])

            elif action == "news":
                code   = action_val.get("code", "")
                name   = action_val.get("name", code)
                from push import notify_newsagent
                msg = (
                    f"请搜索并回复 {name}（{code}）的以下信息：\n"
                    f"1. 公司主营业务简介（2-3句话）\n"
                    f"2. 近期重要公告或财报摘要\n"
                    f"3. 行业地位和核心竞争优势\n"
                    f"4. 近期值得关注的新闻或风险\n"
                    f"请简洁回复，突出关键信息。"
                )
                r = notify_newsagent([msg])
                if r.get("sent"):
                    _reply(client, chat_id,
                           f"📰 已向 AI资讯助手 发送 {name} 的信息查询请求，请稍候查看回复")
                else:
                    _reply(client, chat_id,
                           f"⚠️ 发送失败，请检查 NEWSAGENT_CHAT_ID 配置")

        except Exception as e:
            print(f"[card_action] 处理出错: {e}")

    return on_card_action


# ── 主入口 ───────────────────────────────────────────────────────────────────

def main(once: bool = False):
    if not APP_ID or not APP_SECRET:
        print("❌ 未设置 FEISHU_APP_ID / FEISHU_APP_SECRET，请检查 .env 文件")
        sys.exit(1)

    lark = _get_lark()

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

    eb = (lark.EventDispatcherHandler.builder("", "")
          .register_p2_im_message_receive_v1(_make_handler(client)))
    try:
        eb = eb.register_p2_card_action_trigger(_make_card_handler(client))
        print("[feishu_handler] ✅ 卡片按钮回调已注册")
    except AttributeError:
        print("[feishu_handler] ⚠️ 卡片回调注册失败，文字指令仍可用")
    event_handler = eb.build()

    ws_client = lark.ws.Client(
        APP_ID, APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.WARNING,
    )

    print("[feishu_handler] 🚀 连接飞书 WebSocket 长连接...")
    print("  功能：文字指令 + 卡片按钮（加入关注）+ newsagent 联动")
    print("  发送「帮助」查看所有指令，按 Ctrl+C 停止")
    ws_client.start()


if __name__ == "__main__":
    main(once="--once" in sys.argv)
