# Configuration

The skill holds no repo specifics. It reads them from the repo it is working in, and from a few
settings you control.

## Environment variables

| Variable | Read by | Effect |
|---|---|---|
| `ASF_ALLOW_MAIN_PUSH` | `guard.py` | Comma-separated list of `owner/repo` (meaning github.com) or `host/owner/repo` (case-insensitive, `.git` optional, spaces and empty entries ignored). In a repo where every push URL of `origin` (`git remote get-url --push --all origin`) matches an entry exactly, a Bash call that is only `git push origin <refspec>...` (or `git merge` on main) does not ask, when each refspec that reaches main is written `main`, `master` or `<branch>:main|master`. Bare `git push`, other commands in the same call, wrappers, env assignments, git options other than `-C`, expanded forms (`@`, `HEAD`, `heads/main`, `refs/heads/main`), force pushes and deleting main still ask, and so does everything while a custom ssh command, proxy or receive-pack is configured (`core.sshCommand`, `GIT_SSH_COMMAND` and the like). Details in [guard.md](guard.md#configuration). Default empty: everything asks |
| `ASF_DASHBOARD_PORT` | `dashboard/dashboard.py` | Port, default `4388` |

## Files the skill reads in your repo

| What | File | If missing |
|---|---|---|
| Tracker commands (view, comment, label, PR) | `docs/agents/issue-tracker.md` | Step 0 runs `/setup-matt-pocock-skills`, which asks you and writes it |
| Label strings by role: AFK-ready, human-ready, needs-triage, needs-info, claimed | `docs/agents/triage-labels.md` | Same setup. No `claimed` row: the label `in-progress` is used. `guard.py` also reads this file to learn the name of your AFK-ready label |
| Check, security-test, run-locally, manual-step and smoke commands | `docs/agents/checks.md` | The agent discovers commands from the manifest (`package.json`, etc.), says so, and offers to draft the file |
| Glossary and decisions | `GLOSSARY.md` (older setups: `CONTEXT.md`), `docs/adr/` | Created as you go by `/grill-with-docs` |
| Rules the review learned | `REVIEW.md`, section `## Learned rules` | None yet. Rules are added only with a person's yes, through their own PR |
| House rules | `CLAUDE.md` / `AGENTS.md` | These win over the skill. They are also where the skill finds out where to keep notes |

## Claude Code settings

Edited in `~/.claude/settings.json` (see the [README](../README.md#installation) for the full blocks):

- `hooks.PreToolUse`: the `guard.py` entry.
- `permissions.deny`: `Read(...)` and `Edit(...)` rules for `.env` files.
- `env`: a convenient place to set `ASF_ALLOW_MAIN_PUSH` for Claude Code sessions.

## Work notes

Where the note for a change is kept is decided by your house rules or your global `~/.claude/CLAUDE.md`, for example a notes folder outside the repo, named `YYYY-MM-DD-<slug>.md`. With nothing configured, the note goes in the body of a draft PR. Notes follow the same limits as tickets: no secrets, no personal identifiers, no real client data.

## Models

`MODELS.md` holds the default model per task. Edit its table when your own runs give evidence, and record the change in its log.
