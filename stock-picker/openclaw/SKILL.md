---
name: stock-picker
description: Use this skill when the user sends any stock-related command in Chinese or English: 买入/卖出/持仓/分析/加股/减股/关注列表/查/日报/选股/资讯/新闻/动态/诊断/帮助. Runs local Python scripts to manage a personal stock watchlist, calculate buy points, screen A/HK/US stocks, and search company news. All data stays local; no cloud APIs required beyond market data providers.
---

# Stock Picker Skill

本地股票助手，通过调用 Python 脚本处理选股、持仓、买点分析、公司动态等操作。

## 调用方式

```bash
bash <skill>/scripts/stock.sh <指令> [参数...]
```

将脚本的 stdout 直接作为飞书文本消息回复用户，不要加额外解释。

## 指令映射

| 用户发送 | 调用命令 |
|---|---|
| `帮助` / `stock help` | `bash <skill>/scripts/stock.sh 帮助` |
| `买入 688008 260 100` | `bash <skill>/scripts/stock.sh 买入 688008 260 100` |
| `卖出 688008` | `bash <skill>/scripts/stock.sh 卖出 688008` |
| `持仓` | `bash <skill>/scripts/stock.sh 持仓` |
| `分析` | `bash <skill>/scripts/stock.sh 分析` |
| `加股 600036 招商银行 A` | `bash <skill>/scripts/stock.sh 加股 600036 招商银行 A` |
| `减股 688008` | `bash <skill>/scripts/stock.sh 减股 688008` |
| `关注列表` / `关注` | `bash <skill>/scripts/stock.sh 关注列表` |
| `查 688008` | `bash <skill>/scripts/stock.sh 查 688008` |
| `日报` | `bash <skill>/scripts/stock.sh 日报` |
| `选股` / `选股 HK` / `选股 A 半导体` | `bash <skill>/scripts/stock.sh 选股 [市场] [行业]` |
| `资讯 688008` / `新闻 AAPL US` | `bash <skill>/scripts/stock.sh 资讯 <代码> [市场]` |
| `诊断` | `bash <skill>/scripts/stock.sh 诊断` |

## 注意事项

- HK 代码支持 `HK6082` 或 `06082` 两种格式（脚本自动转换）
- 脚本超时（>60 秒）时先回复「⏳ 正在处理，请稍候...」
- 脚本出错时回复 stderr 的前两行
- 所有分析仅供研究学习，不构成投资建议
