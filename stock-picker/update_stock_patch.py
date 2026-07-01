#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
就地更新已存在的 stock-picker patch（_STOCK_KEYWORDS 和 _is_stock_cmd）。
无需从备份重装，适合升级已打过补丁的 rating-server.py。

用法：
  python3 update_stock_patch.py
  python3 update_stock_patch.py /path/to/rating-server.py
"""
from __future__ import annotations
import sys, shutil
from pathlib import Path
from datetime import datetime

if len(sys.argv) > 1:
    rs_path = Path(sys.argv[1]).expanduser()
else:
    rs_path = (
        Path.home()
        / ".openclaw/agents/ai-news-agent/workspace/scripts/rating-server.py"
    )

if not rs_path.exists():
    print(f"❌ 未找到: {rs_path}")
    sys.exit(1)

src = rs_path.read_text(encoding="utf-8")

if "_STOCK_CMD_PY" not in src:
    print("❌ 该文件没有 stock-picker patch，请先运行 patch_rating_server.py")
    sys.exit(1)

stamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = rs_path.with_suffix(f".bak_{stamp}.py")
shutil.copy2(rs_path, backup)
print(f"✅ 已备份: {backup}")

changed = False

# ── 更新 _STOCK_KEYWORDS ─────────────────────────────────────────────────────
NEW_KEYWORDS = '''\
_STOCK_KEYWORDS = {
    "买入", "卖出", "持仓", "分析", "加股", "减股",
    "关注列表", "关注", "查", "日报", "选股",
    "资讯", "新闻", "动态", "诊断", "帮助", "录入",
}'''

import re
kw_pattern = re.compile(
    r'_STOCK_KEYWORDS\s*=\s*\{[^}]+\}', re.DOTALL
)
m = kw_pattern.search(src)
if m:
    if m.group(0).strip() != NEW_KEYWORDS.strip():
        src = src[:m.start()] + NEW_KEYWORDS + src[m.end():]
        print("✅ _STOCK_KEYWORDS 已更新（新增 录入）")
        changed = True
    else:
        print("ℹ️  _STOCK_KEYWORDS 已是最新")
else:
    print("⚠️  未找到 _STOCK_KEYWORDS，跳过")

# ── 更新 _is_stock_cmd ────────────────────────────────────────────────────────
NEW_IS_STOCK_CMD = '''\
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
    return any(first.startswith(kw) for kw in _STOCK_KEYWORDS if len(kw) >= 2)'''

func_pattern = re.compile(
    r'def _is_stock_cmd\(text: str\) -> bool:.*?return [^\n]+', re.DOTALL
)
m2 = func_pattern.search(src)
if m2:
    if "Prefix match" not in m2.group(0):
        src = src[:m2.start()] + NEW_IS_STOCK_CMD + src[m2.end():]
        print("✅ _is_stock_cmd 已更新（支持前缀匹配）")
        changed = True
    else:
        print("ℹ️  _is_stock_cmd 已是最新")
else:
    print("⚠️  未找到 _is_stock_cmd，跳过")

if changed:
    rs_path.write_text(src, encoding="utf-8")
    print(f"✅ 已写回: {rs_path}")
    print()
    print("下一步：重启 rating-server")
    print("  launchctl kickstart -k \"gui/$(id -u)/ai.openclaw.rating-server\"")
else:
    print("ℹ️  无变更，未写回文件")
