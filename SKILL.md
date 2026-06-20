---
name: shared-vault-workflow
description: Set up and maintain a portable multi-device AI workspace built on a shared Obsidian vault, with secret-safe redaction, wiki/raw/MEMORY/log classification, and consistent logging rules. Use when a user wants a transferable workflow for Codex, Claude, OpenClaw, or similar agents across multiple devices and team members.
---

# Shared Vault Workflow

Use this skill when building or sharing a cross-device AI workspace around one shared vault.

## Core rules

- Treat the vault as the shared source of truth.
- Keep device-specific paths, auth, cookies, API keys, tokens, passwords, and recovery codes local.
- Never copy personal identifiers into shared skill files unless the user explicitly wants a private version.
- Prefer one portable folder layout that works on any machine.

## First decision

Before doing anything else, classify the task as one of:

- bootstrap: set up a new device or a new teammate
- maintain: classify new material, log work, or update knowledge
- export: prepare a clean shareable version for other people

If the task spans more than one of these, do bootstrap first, then maintain, then export.

## Portable folder model

See [folder-map.md](references/folder-map.md) for the standard layout.

The default pattern is:

- `raw/` for original material
- `wiki/` for cleaned reusable knowledge
- `MEMORY.md` for stable decisions, preferences, and project state
- `logs/` for dated work records
- `Resources/` for reference material and templates

## Maintenance workflow

See [maintenance.md](references/maintenance.md) for the operational rules.

Use this order:

1. Put raw material into `raw/`.
2. Convert reusable knowledge into `wiki/`.
3. Append lasting decisions to `MEMORY.md`.
4. Write the work result into a dated `logs/YYYY-MM-DD-*.md` file.
5. Update the top-level status note if the workspace uses one.

## Redaction workflow

See [redaction.md](references/redaction.md) before exporting or sharing.

Before packaging for another person:

- replace real names, emails, hostnames, machine names, and account IDs with placeholders
- remove all secret material
- replace absolute personal paths with generic placeholders
- keep only structural examples, not live credentials or private data

## Cross-device setup

For each new device:

1. Point the agent to the same vault root.
2. Install the shared skill set.
3. Keep local secrets local.
4. Verify that the agent reads the portable rules first, not a machine-specific override.

## Good triggers

This skill should trigger for prompts about:

- shared vaults
- cross-device AI workspaces
- team knowledge base setup
- wiki/raw/MEMORY/log structure
- packaging a private workflow into a shareable template
- redacting secrets before sharing a workflow

