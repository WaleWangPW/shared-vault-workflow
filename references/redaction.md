# Redaction

Use this checklist before sharing a workflow with another person.

## Remove

- API keys
- OAuth codes
- cookies
- passwords
- recovery codes
- tokens
- personal email addresses
- hostnames tied to one machine
- local absolute paths tied to one person

## Replace with placeholders

- `YOUR_NAME`
- `YOUR_EMAIL`
- `YOUR_DEVICE`
- `YOUR_VAULT_ROOT`
- `YOUR_TEAM`
- `YOUR_LOCAL_SECRET_STORE`

## Keep

- folder structure
- rules
- examples without secrets
- classification logic
- logging format

## Verify

- no secret values remain in SKILL.md
- no private machine names remain
- no personal account details remain
- no current production tokens remain

