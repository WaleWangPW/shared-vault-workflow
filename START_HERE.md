# 快速开始

这是给人看的最短版。

## 你需要做什么

1. 把这个仓库交给你的 AI agent，或者把里面的说明发给同事。
2. 让它先读 `AGENT_PROMPT_zh.md`。
3. 让它按 `raw / wiki / MEMORY / logs` 的规则整理资料。
4. 如果要公开给别人，先读 `references/redaction.md`、`references/logs-safety.md` 和 `references/resources-checklist.md`。
5. 发布前跑一下 `scripts/check-secrets.sh`。

## 最重要的规则

- 原始资料先进 `raw/`
- 整理后的知识进 `wiki/`
- 会影响以后判断的稳定结论进 `MEMORY.md`
- 当天过程进 `logs/`
- 任何密钥、cookie、token、密码都不要发出来

## 适合谁

- 想把多设备 AI 工作流标准化的人
- 想把知识库整理给同事的人
- 想把工作流做成可转发模板的人
