# 对外转发包清单（中文）

这是一份给同事、外部团队或任何本地 agent 复用的安全清单。

## 可以发

只发这些通用模板和说明：

```text
shared-vault-workflow/
├── SKILL.md
└── references/
    ├── folder-map.md
    ├── maintenance.md
    ├── onboarding-zh.md
    └── redaction.md
```

推荐再加上：

```text
├── AGENT_PROMPT_zh.md
├── START_HERE.md
├── QUICKSTART.md
├── references/logs-safety.md
├── references/resources-checklist.md
└── scripts/check-secrets.sh
```

如果需要补一个仓库首页说明，可以额外加一个极简 `README.md`，但不要放个人资料。

## 不要发

以下内容不要放到对外包里：

- 你的真实 Vault 全量内容
- 任何 API key、OAuth code、cookie、token、密码、恢复码
- 任何 `~/.ai-vault`、`~/.claude`、`~/.openclaw` 之类本机配置
- 任何带真实姓名、邮箱、机器名、内网地址的文件
- 任何只属于你个人工作流的会话记录或日志

## 看情况发

这些内容只有在完全脱敏后才考虑发：

- 你自己的规则总结
- 通用流程示例
- 目录结构图
- 命名规范
- 分类方法

原则是：只发“方法”，不发“你的私人资料”。

## 推荐仓库结构

```text
shared-vault-workflow/
├── SKILL.md
├── AGENT_PROMPT_zh.md
├── START_HERE.md
├── QUICKSTART.md
├── references/
│   ├── folder-map.md
│   ├── maintenance.md
│   ├── onboarding-zh.md
│   ├── redaction.md
│   ├── logs-safety.md
│   └── resources-checklist.md
└── scripts/
    └── check-secrets.sh
└── README.md   # 可选，且必须是脱敏版
```

## 发布前检查

发布前逐项确认：

- 文件里没有真实姓名
- 文件里没有邮箱
- 文件里没有设备名
- 文件里没有本地绝对路径
- 文件里没有任何密钥或登录码
- 文件里没有可识别你个人环境的细节

如果有一项不能确认，就不要发。
