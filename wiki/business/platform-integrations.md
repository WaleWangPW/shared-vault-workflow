# 平台集成设计：Obsidian + Notion

> 分类：#product/architecture  #可公开 ✅
> 最后更新：2026-06-27

---

## 一、为什么要同时支持两个平台

| 工具 | 最适合的场景 | 用户类型 |
|------|------------|---------|
| **Obsidian** | 个人深度研究、私有知识库、跨 Agent 协作 | 自己 + 高级用户 |
| **Notion** | 团队协作、客户汇报、公开分享、标准化模板 | 团队 + 客户 |

两者不是替代关系，而是分层：
```
原始分析 / 私有笔记 → Obsidian（本地加密，绝不公开）
         ↓ 脱敏 + 精炼
客户报告 / 团队共享 → Notion（结构化，可控权限）
```

---

## 二、集成方式

### Obsidian 集成（已部分实现）

| 方案 | 状态 | 说明 |
|------|------|------|
| Local REST API + ngrok | 受云端代理限制，暂不稳定 | 见 HANDOFF |
| Git 同步（shared-vault-workflow） | ✅ 当前方案 | 推 git → Obsidian 同步 |
| Obsidian Sync 官方 | 付费，可跨设备 | 最稳定但不能让 Agent 写入 |

**输出到 Obsidian 的内容：**
- 每日选股日报 → `logs/YYYY-MM-DD-stock-daily.md`
- 个股深度研究 → `wiki/stocks/股票代码.md`
- 买点/止损触发记录 → `logs/YYYY-MM-DD-alerts.md`

---

### Notion 集成（待实现）

Notion 有完整的公开 API，支持读写页面和数据库。

**接入方式：**
```python
# 环境变量（绝不硬编码）
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

# Notion API endpoint
POST https://api.notion.com/v1/pages
Authorization: Bearer {NOTION_TOKEN}
```

**适合写入 Notion 的内容：**
- 选股候选看板（Database 视图，可筛选/排序）
- 客户报告页面（精炼版，无敏感数据）
- 待办/决策追踪（与团队协作）
- 公开的研究结论（设为 Public 后可分享链接）

---

## 三、数据流设计

```
选股系统 (run_daily.py)
        │
        ├─► Obsidian (via git)
        │    raw/daily/           ← 完整原始日报
        │    logs/alerts/         ← 实时监控触发
        │    wiki/stocks/         ← 个股深度页
        │
        └─► Notion (via API)
             📊 选股看板          ← 候选股 Database
             📄 客户报告页        ← 脱敏后的分析结论
             ✅ 决策日志          ← 买入/卖出记录
```

**信息分级与流向：**
```
#客户专属 🔒 → 只存本地 Obsidian，永不进 Notion
#内部 🟡     → 可进 Notion 私有工作区
#公开 ✅     → 可进 Notion 并设为 Public 共享
```

---

## 四、实现优先级

| 优先级 | 功能 | 工作量 |
|--------|------|--------|
| P0 | Obsidian git 同步（现有）| 已完成 |
| P1 | run_daily 输出 `.md` 文件到 git | 小，约 1 天 |
| P2 | Notion 选股看板写入 | 中，约 2-3 天 |
| P3 | Notion 客户报告页自动生成 | 中，约 2 天 |
| P4 | 双向同步（Notion → Obsidian） | 大，暂不急 |

---

## 五、技术要点

### Notion Database 字段设计（选股看板）
```
股票名称     (Title)
代码         (Text)
市场         (Select: A/HK/US)
综合得分     (Number)
建议买点     (Number)
止损位       (Number)
目标价       (Number)
触发信号     (Multi-select)
更新日期     (Date)
状态         (Select: 候选/持仓/已出/观察)
```

### Obsidian 个股页模板
```markdown
# {股票名称} ({代码})

> 市场: {A/HK/US}  更新: {日期}
> 标签: #stock/{行业} #{状态}

## 基本面
...

## 买点分析
...

## 历史记录
...
```

---

## 待决策

- [ ] Notion 工作区是个人版还是团队版（影响权限设计）
- [ ] 是否需要客户直接访问 Notion 看板（还是只发截图/PDF）
- [ ] Obsidian 个股页是否要和 Notion 保持同步（双写还是单向）
