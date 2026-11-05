# guard.py

`guard.py` is a [Claude Code `PreToolUse` hook](https://code.claude.com/docs/en/hooks). Before Claude runs a Bash command or one of a few deploy-type MCP tools, Claude Code pipes the call to the script as JSON on stdin. If the call is one that only a person may approve, the script answers with `permissionDecision: "ask"`; Claude Code then shows you an approval prompt with the reason ("Only a person approves this: ..."). Otherwise it prints nothing and the call proceeds under your normal permission rules.

![Sequence: agent, Claude Code, guard.py, person approves or denies](diagrams/guard.svg)

Standard-library Python 3.7+ and `git` on PATH. Self-test: `python3 guard.py --check` (prints `ok`).

## What it asks about

| Action | Examples it recognizes |
|---|---|
| Merge | `gh pr merge`, the pulls merge API via `gh api`, `git merge` while the current branch is main (not `--abort`, `--quit` or `--ff-only`) |
| Push to main | `git push` whose refspec destination (or the source, for a refspec without `:`) has `main` or `master` as its last path component, case-insensitive: `main`, `feature:main`, `heads/main`, `refs/heads/main`, `feature:heads/master`, and also `feature/main` or `refs/remotes/origin/main`. `@` and `HEAD` (any case, since macOS resolves `head` too) count as the current branch, so `git push origin @` or a bare `git push` while on main asks. When git picks the destination from config, it asks too: any push in a repo with `remote.<name>.push` set, a push with no refspec under `push.default=matching`, and a refspec without `:` under `push.default=upstream` whose branch tracks main; a name with `@{` (such as `@{-1}`), `~` or `^` asks because the branch cannot be told. Wrapped forms (`env`, `timeout`, `xargs`, `bash -c`, `eval`, command substitution) are read too |
| Force push or bulk push | `git push` with `-f`, `--force*`, `--mirror`, `--all`, a `+` refspec, a lone `:` refspec or a `*` refspec |
| Deleting main | `git push origin :main`, `git push --delete origin main`, `git push -d origin master` and the like. Deleting any other branch (`git push origin :feature`, `--delete origin feature`) does not ask |
| Deploy | `vercel`, `netlify deploy`, `wrangler deploy`, `fly deploy`, `railway up`, `firebase deploy`, `npm/pnpm/yarn/bun publish` and `deploy` scripts, `gh workflow run`, and MCP tools named like `deploy_*`, `create_deployment`, `request_promote`, `request_rollback`, `assign_alias` and the rolling-release start/complete/approve tools |
| Real migrations | `supabase db push` / `functions deploy` / `migration up`, `prisma migrate deploy` / `db push`, `drizzle-kit push` / `migrate` (a `--dry-run` is not asked) |
| The AFK label | Applying the "ready for an agent" label through `gh` or `glab` (it is the Gate 1 approval). The label string is `ready-for-agent` plus the name your repo gives that role in `docs/agents/triage-labels.md`. A description that merely contains the label text may also ask. The file is read only if it is a regular file (not a symlink, device or FIFO), and at most 20000 bytes of it; if it exists but cannot be read that way, applying any label through `gh`/`glab` asks |
| `.env` files via the shell | Any argument that names `.env`, `.env.*` or `*.env` (`cat`, `source`, redirects, globs like `.en?`). `.env.example`, `.sample`, `.template`, `.dist` and `.defaults` are not asked |

It also reads inside `sh`/`bash`/`zsh -c` strings, `eval`, command substitutions and heredocs that a shell receives. A command it cannot parse that mentions push, merge, deploy or `.env` asks. If the script itself crashes, it asks; it never lets a call through silently because it broke.

## Configuration

`ASF_ALLOW_MAIN_PUSH` is a comma-separated list of repos whose pushes to main do not ask. Unset or empty (the default): everything asks.

- **Entry format.** `owner/repo` means `github.com/owner/repo`; for another host write `host/owner/repo` (for example `acme/notes,git.example.com/team/wiki`). Case-insensitive, a trailing `.git` is optional, spaces and empty entries are ignored.
- **Which repo.** The guard asks git for the URLs it will really push to, `git remote get-url --push --all origin` (this honors `pushurl`, extra URLs added with `git remote set-url --add`, and `insteadOf`/`pushInsteadOf`). Every one of them must match an entry exactly, host and `owner/repo` (a port is ignored). Recognized URL forms: `https://host/owner/repo`, `ssh://user@host/owner/repo` and `user@host:owner/repo`, each with or without `.git`. Anything else (`http://`, `file://`, local paths, extra path segments, `%`, `?`, `#` or a second `@` in the URL, a look-alike like `acme/notes-evil`) does not match.
- **Which command.** Only when the whole Bash call is exactly `git push origin <refspec>...`: a literal `git`, `origin` named explicitly, at least one refspec, no flags other than `-u`/`--set-upstream`, `-q`, `-v`, `--progress` and `--atomic`, and no git option before `push` other than `-C <dir>` (the guard resolves the directory). Any of these drops the exception, so a push to main asks as usual: a bare `git push` or `git push origin`, another command in the same call (`cd ... &&`, `;`, pipes, redirections), a wrapper (`env`, `timeout`, `bash -c`...), an environment assignment (`GIT_DIR=...`), `-c`, `--git-dir`, `--work-tree`, `--exec-path`, `--repo`, `$variables`, globs or braces.
- **Which refspec.** Each refspec that reaches main must be written literally as `main`, `master` or `<branch>:main` / `<branch>:master` (`HEAD:main` included). Forms that git expands to main ask even in a listed repo: `@`, `@:main`, `HEAD` alone, `heads/main`, `refs/heads/master`, `feature:heads/main`, `feature:Main`.
- **Which settings.** The exception is refused while git could send the push somewhere other than the URL checked: any of `core.sshCommand`, `core.gitProxy`, `remote.origin.receivepack`, `remote.origin.vcs`, `remote.origin.proxy`, `http.proxy`, `http.<url>.proxy` or `http.sslVerify` set in any config scope (read with `git config --get-regexp` in the repo, so values passed through `GIT_CONFIG_COUNT` or `GIT_CONFIG_PARAMETERS` count), or `GIT_SSH`, `GIT_SSH_COMMAND`, `GIT_PROXY_COMMAND`, `GIT_EXEC_PATH` or `GIT_CONFIG` present in the environment Claude Code runs the hook in. Then pushes to main ask as usual.
- **Merge too.** In a listed repo, a `git merge` on main that meets the same command rules (alone in the call, a literal `git`, only `-C` before `merge`, no `$`, globs or braces) does not ask either.
- **Never skipped.** Force pushes, bulk pushes and deleting main ask even in a listed repo.

The check reads git's config as it is when the call is made. It does not inspect git hooks (`pre-push`, `core.hooksPath`), credential helpers, your `~/.ssh/config` (a `Host github.com` entry can point ssh elsewhere), environment variables your shell profile sets for the Bash tool but that the hook process does not see, or what the server does with the push. Set the variable in the environment Claude Code runs in, for example in the `env` block of `~/.claude/settings.json`.

## Install

See the [README](../README.md#4-install-the-guard-hook) for the exact `settings.json` blocks (the hook entry and the `.env` deny rules). The hook command path assumes the skill lives at `~/.claude/skills/ai-software-factory/`.

The matcher is `Bash|mcp__.*__(deploy_.*|...)`. Claude Code treats a matcher containing characters beyond letters, digits, `_`, `-`, spaces, `,` and `|` as a JavaScript regular expression, tested unanchored against the tool name.

## What the `.env` deny rules add

The hook sees shell commands. Claude's file tools (Read, Edit, Write) are not shell commands, so `permissions.deny` covers them. `Edit` rules apply to all built-in tools that edit files. `Read` rules are applied best-effort to tools such as Grep and Glob. Rules using the `//` prefix are absolute paths from the filesystem root, so `Read(//**/.env)` matches a `.env` anywhere on the machine.

## Honest limits

- **It reads text; it does not run or sandbox anything.** An alias, a script that does the push inside, `python -c`, or any tool that performs the action internally is not seen. It stops mistakes and instructions hidden in tickets, not a determined attacker. The real ceiling is a sandbox per agent.
- **Claude Code only.** Codex, Gemini and other agents have no such block; for them the rule is text in `SKILL.md`, and they review read-only and do not build.
- **No commit tracking.** "An approval holds for one commit" is a rule for the agent, not something the hook enforces.
- **The prompt is a human decision.** If you approve everything without reading, nothing protects you. When nobody is at the keyboard, the agent waits on its own and others keep going.
- **A blocked step is finished.** The agent is told to hand it back and never look for another route to the same effect.
