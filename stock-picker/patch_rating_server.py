#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patches rating-server.py so that stock commands are routed to stock-picker/cmd.py
BEFORE the existing news/LLM logic runs.

Usage:
  python3 patch_rating_server.py
  python3 patch_rating_server.py /path/to/rating-server.py
"""
from __future__ import annotations
import re, sys, shutil, os
from pathlib import Path
from datetime import datetime

# ── Locate rating-server.py ───────────────────────────────────────────────────
if len(sys.argv) > 1:
    rs_path = Path(sys.argv[1]).expanduser()
else:
    rs_path = (
        Path.home()
        / ".openclaw/agents/ai-news-agent/workspace/scripts/rating-server.py"
    )

if not rs_path.exists():
    print(f"❌ 未找到 rating-server.py: {rs_path}")
    print("   用法: python3 patch_rating_server.py [path/to/rating-server.py]")
    sys.exit(1)

print(f"目标文件: {rs_path}")

# ── Backup ────────────────────────────────────────────────────────────────────
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = rs_path.with_suffix(f".bak_{stamp}.py")
shutil.copy2(rs_path, backup)
print(f"✅ 已备份: {backup}")

# ── Read source ───────────────────────────────────────────────────────────────
src = rs_path.read_text(encoding="utf-8")

# ── Guard: already patched? ───────────────────────────────────────────────────
if "_STOCK_CMD_PY" in src:
    print("ℹ️  已检测到 stock-picker 补丁，无需重复打补丁")
    print("   如需重新打补丁，请先从备份恢复原文件")
    sys.exit(0)

# ── Ensure `import subprocess` is present ────────────────────────────────────
if "import subprocess" not in src:
    # Insert after first `import os` or at the first import line
    if "import os" in src:
        src = src.replace("import os\n", "import os\nimport subprocess\n", 1)
    else:
        lines = src.splitlines(keepends=True)
        for i, ln in enumerate(lines):
            if ln.startswith("import ") or ln.startswith("from "):
                lines.insert(i, "import subprocess\n")
                break
        src = "".join(lines)
    print("✅ 已添加 import subprocess")

# ── Stock handler code (injected just before handle_message_receive) ──────────
STOCK_HANDLER = '''
# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  stock-picker 路由（由 patch_rating_server.py 注入）                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
_STOCK_DIR    = os.path.expanduser("~/shared-vault-workflow/stock-picker")
_STOCK_CMD_PY = os.path.join(_STOCK_DIR, "cmd.py")
_STOCK_VENV   = os.path.join(_STOCK_DIR, ".venv", "bin", "python3")

_STOCK_KEYWORDS = {
    "买入", "卖出", "持仓", "分析", "加股", "减股",
    "关注列表", "关注", "查", "日报", "选股",
    "资讯", "新闻", "动态", "诊断", "帮助", "录入",
}


def _is_stock_cmd(text: str) -> bool:
    """Return True if text starts with a known stock command keyword."""
    # Skip leading @-mentions so group-chat messages like '@bot 帮助' also match
    words = [w for w in text.split() if not w.startswith("@")]
    if not words:
        return False
    first = words[0]
    # Exact match (e.g. "持仓", "帮助")
    if first in _STOCK_KEYWORDS:
        return True
    # Prefix match: handles natural phrasing like "关注美股Circle" or "持仓情况"
    return any(first.startswith(kw) for kw in _STOCK_KEYWORDS if len(kw) >= 2)


def _run_stock_cmd(text: str) -> None:
    """Execute cmd.py with the user's arguments and send the result to Feishu."""
    parts = text.strip().split()
    py_bin = _STOCK_VENV if os.path.exists(_STOCK_VENV) else "python3"
    if not os.path.exists(_STOCK_CMD_PY):
        _send_feishu_text("❌ 找不到股票脚本: " + _STOCK_CMD_PY)
        return
    try:
        result = subprocess.run(
            [py_bin, _STOCK_CMD_PY] + parts,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=_STOCK_DIR,
        )
        reply = (result.stdout or result.stderr or "❌ 无输出").strip()
    except subprocess.TimeoutExpired:
        reply = "⏳ 处理超时（>120s），请稍后重试"
    except Exception as exc:  # noqa: BLE001
        reply = "❌ 股票脚本出错：" + str(exc)
    if reply == "__CARD_SENT__":
        return  # cmd.py 已直接发送飞书卡片，无需重复推送
    _send_feishu_text(reply)
# ── /stock-picker 路由 ────────────────────────────────────────────────────────

'''

# ── Inject stock handler before handle_message_receive ───────────────────────
handler_pattern = r"(def handle_message_receive\()"
if re.search(handler_pattern, src):
    src = re.sub(handler_pattern, STOCK_HANDLER + r"\1", src, count=1)
    print("✅ 已注入 _is_stock_cmd / _run_stock_cmd 函数")
else:
    print("❌ 未找到 'def handle_message_receive(' — 请检查文件结构")
    sys.exit(1)

def _make_routing(indent: str) -> str:
    """Build the stock-routing snippet with the correct indentation."""
    i = indent
    i2 = indent + "    "
    return (
        f"{i}# ── stock 指令优先路由 ──────────────────────────────────────────────────\n"
        f"{i}if _is_stock_cmd(text):\n"
        f"{i2}_run_stock_cmd(text)\n"
        f"{i2}return\n"
        f"{i}# ── /stock 路由 ─────────────────────────────────────────────────────────\n"
    )


# Strategy 1: insert after `if not text:` + return/continue block, but only
# inside handle_message_receive (search only from that function's position).
_hmr_start = src.index("def handle_message_receive(")
_NOT_TEXT_RE = re.compile(
    r"([ \t]*if not text:[ \t]*\n[ \t]+(?:return|continue)[^\n]*\n)"
)
m = _NOT_TEXT_RE.search(src, _hmr_start)
if m:
    indent = re.match(r"([ \t]*)", m.group(1)).group(1)
    routing = _make_routing(indent)
    src = src[: m.end()] + routing + src[m.end() :]
    print("✅ 已在 'if not text: return' 之后注入 stock 路由")
else:
    # Strategy 2: insert after text extraction line
    _TEXT_EXTRACT_RE = re.compile(
        r"([ \t]*text\s*=\s*content\.get\(['\"]text['\"][^\n]*\n)"
    )
    m2 = _TEXT_EXTRACT_RE.search(src)
    if m2:
        indent = re.match(r"([ \t]*)", m2.group(1)).group(1)
        routing = _make_routing(indent)
        src = src[: m2.end()] + routing + src[m2.end() :]
        print("✅ 已在文本提取行之后注入 stock 路由（回退方式）")
    else:
        sample = _make_routing("        ")  # 8-space example for manual guidance
        print(
            "⚠️  未找到自动注入点。请手动将以下代码添加到 handle_message_receive()"
            " 中、文本提取之后："
        )
        print(sample)

# ── Write back ────────────────────────────────────────────────────────────────
rs_path.write_text(src, encoding="utf-8")
print(f"✅ 已更新: {rs_path}")
print()
print("下一步：重启 openclaw ai-news-agent 以加载更改")
print("  cd stock-picker && bash install_feishu_stock_patch.sh --restart-only")
print("  或手动: launchctl unload ~/Library/LaunchAgents/*openclaw*.plist && \\")
print("         launchctl load   ~/Library/LaunchAgents/*openclaw*.plist")
