# Logs Safety

Use this guide before writing anything into `logs/` that may be shared with another person, another device, or another agent.

## What logs are for

Logs should answer:

- what happened
- what was verified
- what failed
- what should happen next
- who should pick up the work

Logs should not become a secret dump.

## Safe to record

- task names
- dates
- steps taken at a high level
- verification results
- file names without private content
- placeholders such as `YOUR_TOKEN` or `YOUR_DEVICE`
- handoff notes

## Do not record

- API keys
- OAuth codes
- cookies
- passwords
- recovery codes
- tokens
- access headers
- full raw API responses when they contain private fields
- personal email addresses
- machine names tied to one person
- local absolute paths tied to one environment

## Good pattern

```text
Verified Claude handoff through shared HANDOFF.md.
Next step: continue from the current task state.
Sensitive values were not written to the log.
```

## Bad pattern

```text
curl -H "Authorization: Bearer abc123..."
```

## Redaction rule

If a log entry needs context, redact the sensitive part before saving it:

- `Bearer abc123...` → `Bearer [REDACTED]`
- `/Users/alice/projects/vault` → `YOUR_VAULT_ROOT`
- `alice@example.com` → `YOUR_EMAIL`

## Final check

Before saving a log entry, ask:

1. Would I be comfortable showing this to a teammate?
2. Would this still be safe if the repo became public?
3. Does this reveal anything that should stay local?

If the answer to any of these is no, redact more.
