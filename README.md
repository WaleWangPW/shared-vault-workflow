# Shared Vault Workflow

Build one shared, secret-safe knowledge base that works across devices, agents, and teammates.

This repo is a portable starter kit for Obsidian-based AI workspaces. It shows how to keep raw material, reusable knowledge, durable memory, and work logs in clear separate lanes so any supported agent can pick up the same workspace on a different machine.

## What this gives you

- A clean folder model for shared workspaces
- A simple ruleset for `raw / wiki / MEMORY / logs / Resources`
- A safe redaction checklist for sharing with other people
- A Chinese onboarding page for non-technical users
- A direct agent bootstrap prompt for systems that do not support skills
- A logs safety guide and a resources publishing checklist
- A lightweight secret scan script for pre-share review

## Who it is for

- People who want one knowledge base across multiple devices
- Teams that want to hand the same workflow to different agents
- Users who want to publish a reusable, secret-safe workflow template
- Anyone who wants a practical structure instead of a pile of notes

## How to use it

1. Open [START_HERE.md](START_HERE.md) if you are a human.
2. Open [AGENT_PROMPT_zh.md](AGENT_PROMPT_zh.md) if you are an AI agent.
3. If your environment supports skills, use [SKILL.md](SKILL.md).
4. If your environment does not support skills, follow the reference files directly.

## Contents

- `SKILL.md`: skill-aware workflow for shared vaults
- `START_HERE.md`: short human-facing starting point
- `AGENT_PROMPT_zh.md`: direct bootstrap prompt for any agent
- `references/folder-map.md`: portable folder layout
- `references/maintenance.md`: what goes where and in what order
- `references/onboarding-zh.md`: Chinese onboarding guide
- `references/redaction.md`: how to remove secrets before sharing
- `references/logs-safety.md`: what is safe to write into logs
- `references/resources-checklist.md`: how to decide what belongs in Resources
- `references/export-package-zh.md`: what to publish and what to keep private
- `scripts/check-secrets.sh`: quick scan for obvious secret patterns

## The core idea

Keep the workspace simple:

- `raw/` for original inputs
- `wiki/` for reusable knowledge
- `MEMORY.md` for stable decisions and project state
- `logs/` for dated activity
- `Resources/` for templates and references

The goal is not just to store notes. The goal is to make the same workspace usable on any device and by any supported agent without leaking private details.

## Safety rule

Only publish the reusable method.

Do not publish:

- API keys
- cookies
- OAuth codes
- tokens
- passwords
- recovery codes
- private machine names
- private absolute paths
- private workspace contents

If you want a more polished rollout, share this repo together with `START_HERE.md` and `AGENT_PROMPT_zh.md` so the recipient gets both the human summary and the agent bootstrap prompt.

## If you want to share this repo

Send the repo link together with:

- [START_HERE.md](START_HERE.md)
- [AGENT_PROMPT_zh.md](AGENT_PROMPT_zh.md)

That is enough for a person or agent to understand the workflow without knowing anything about your private environment.
