# EliteMining — Claude Code Instructions

All shared project rules live in AGENTS.md (also read by Codex). Add short shared rules there (details go in docs/), not here or in memory.

@AGENTS.md

## Claude Only

- At a task boundary, when the user moves to an unrelated task or starts a new release, add one line saying it's a good point to type `/clear` (Claude can't run it, and the user's usage limits are shared). Don't suggest it for follow-ups on the same task.
