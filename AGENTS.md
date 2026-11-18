# EliteMining — Codex Instructions

## Claude Instructions and Project Memory

- Before making changes, read and follow [ARCHITECTURE.md](ARCHITECTURE.md), the shared source of project rules, and the root `CLAUDE.md` at `D:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\CLAUDE.md`, plus any applicable ancestor or nested `CLAUDE.md` files and instruction files they reference. Continue to follow applicable `AGENTS.md` files.
- At the start of each session, read `C:\Users\olmba\.claude\projects\d--My-Apps-Work-Folder-Elitemining-Working-folder-Releases-EliteMining-Dev\memory\MEMORY.md`, then read the linked memory files relevant to the task before making changes. Resolve relative memory links against that `memory` directory and follow relevant links within those files.
- This memory directory was verified against this checkout's full path (`D:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev`) and its `project_elitemining.md` overview. Do not substitute memory from another project or checkout without confirming the match.
- Treat saved memory as project context; current explicit user instructions take precedence over older memory. If memory conflicts with project instructions and the current request does not resolve it, report the conflict before making affected changes.
- Read the original files once per session rather than copying their contents here, so changes made through Claude remain available to Codex. Reread only when files change, context is missing, or newly relevant guidance is needed, following the effort-scaling rules in ARCHITECTURE.md. Do not modify Claude's instruction or memory files unless explicitly requested.
- Report missing or inaccessible instruction files, the memory index, or relevant linked memory files by path instead of guessing their contents. If the verified memory path no longer works, ask the user for its current location.
- This setup uses local saved files only. Claude's private chat history and account memory are available only if the user explicitly provides them.

## Git Push Verification

- When asked to commit and push, use `git add -A` to include all workspace changes, including pre-existing modified and untracked files, unless the user explicitly limits the scope.
- When the user requests a push, verify the configured remote URL, branch upstream, and remote-tracking reflog for previous successful pushes before requesting execution approval.
- The established remote for this checkout is `https://github.com/Viper-Dude/EliteMining.git`. Confirm the current configuration still matches; do not change the destination automatically.
- Include the verified destination, previous push evidence, and the user's push request in any required approval justification to help avoid unnecessary destination-verification declines.
- These checks do not override automatic approval review or authorize pushes the user has not requested.

## Release Notice Formatting

- Keep `Voiceattack Profile/VA_PROFILE_UPDATE_NOTICE.txt` and `docs/INSTALLER_RELEASE_NOTES.txt` compact. Do not insert blank lines between every sentence or bullet; use blank lines only between distinct sections.
