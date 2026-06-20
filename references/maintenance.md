# Maintenance

## Daily flow

1. Read the portable rules first.
2. Identify the domain.
3. Store source material in `raw/`.
4. Promote reusable material to `wiki/`.
5. Append only durable facts to `MEMORY.md`.
6. Write a dated log entry.

## What belongs where

- `raw/`: unedited articles, transcripts, screenshots, exports, notes from capture
- `wiki/`: entities, concepts, summaries, synthesized guidance, how-tos
- `MEMORY.md`: decisions, preferences, current project status, long-lived facts
- `logs/`: action history, verification notes, handoff notes

## Query behavior

When answering from the knowledge base:

- read the index first
- then read only the few most relevant pages
- do not scan everything
- if the answer would change future behavior, consider promoting it into wiki or MEMORY

