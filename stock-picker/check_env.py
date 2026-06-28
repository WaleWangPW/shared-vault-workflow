#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
部署前环境检查。运行：python3 check_env.py
检查项：必须/可选环境变量、依赖库、数据源连通性（取一只 A 股行情）。
"""
import os, sys

OPTIONAL_ENVS  = ["TUSHARE_TOKEN", "FEISHU_WEBHOOK_URL",
                  "FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_CHAT_ID"]
TEST_CODE      = "688008"
TEST_MARKET    = "A"

ok = True

print("=" * 50)
print("  选股系统 - 环境检查")
print("=" * 50)

# ── 1. 环境变量 ──────────────────────────────────────────────
print("\n[1] 环境变量")
for key in OPTIONAL_ENVS:
    val = os.environ.get(key, "")
    if val:
        masked = val[:4] + "****" + val[-2:] if len(val) > 6 else "****"
        print(f"  ✓ {key} = {masked}")
    else:
        print(f"  ○ {key} 未设置")

webhook_set = bool(os.environ.get("FEISHU_WEBHOOK_URL", "").strip())
app_set = all(os.environ.get(k, "").strip()
              for k in ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_CHAT_ID"))
feishu_set = webhook_set or app_set
if not feishu_set:
    print("  ⚠  飞书推送未配置 → --dry-run 模式可正常运行")
else:
    mode = "webhook" if webhook_set else "app API"
    print(f"  ✓ 飞书推送模式: {mode}")

# ── 2. 依赖库 ────────────────────────────────────────────────
print("\n[2] 依赖库")
deps = {
    "akshare":   ("akshare",    True),   # (模块名, 是否必须)
    "pandas":    ("pandas",     True),
    "tushare":   ("tushare",    False),
    "lark-oapi": ("lark_oapi",  False),  # 飞书双向交互层需要
}
for pkg, (mod, required) in deps.items():
    try:
        __import__(mod)
        print(f"  ✓ {pkg}")
    except ImportError:
        tag = "必须" if required else "可选"
        print(f"  {'✗' if required else '○'} {pkg} 未安装（{tag}）  pip install {pkg}")
        if required:
            ok = False

# ── 3. 数据源连通性 ──────────────────────────────────────────
print("\n[3] 数据源连通性（取 688008 近 5 日行情）")
try:
    from data_source import get_source
    src = get_source()
    print(f"  数据源: {src.name}")
    prices = src.get_daily(TEST_CODE, TEST_MARKET, 5)
    if prices:
        print(f"  ✓ 取到 {len(prices)} 条价格，最新收盘价 {prices[-1]:.2f}")
    else:
        print("  ✗ 返回空数据（网络或接口异常）")
        ok = False
except Exception as e:
    print(f"  ✗ 连通性测试失败: {e}")
    ok = False

# ── 4. 飞书推送测试 ──────────────────────────────────────────
print("\n[4] 飞书推送")
if feishu_set:
    try:
        from push import send_feishu
        r = send_feishu("[check_env] 飞书推送测试 ✓（忽略此消息）")
        if r.get("sent"):
            print(f"  ✓ 推送成功")
        else:
            print(f"  ✗ 推送失败: {r.get('reason')}")
            ok = False
    except Exception as e:
        print(f"  ✗ 推送异常: {e}")
        ok = False
else:
    print("  ○ 跳过（未配置飞书推送）")

# ── 结果 ─────────────────────────────────────────────────────
print("\n" + "=" * 50)
if ok:
    print("  全部检查通过 ✅  可以部署！")
else:
    print("  存在问题 ❌  请修复后重新运行")
print("=" * 50)
sys.exit(0 if ok else 1)
