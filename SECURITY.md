# Security policy

## Reporting a vulnerability

Use GitHub private vulnerability reporting: open this repository's **Security** tab, choose
**Report a vulnerability**, and fill in the form. Please do not open a public issue for a
vulnerability.

A report is most useful with: what you ran, what you expected, what happened, and a command or
input that reproduces it (for `guard.py`, the exact command string that got through).

## What counts

- A command `guard.py` is meant to stop (see [docs/guard.md](docs/guard.md)) that runs without
  asking, when it is written in an ordinary, direct way.
- A way for a web page to make the dashboard act despite its token and Host/Origin checks, or to
  reach it from outside `127.0.0.1`.
- A path by which the skill's text makes an agent act on instructions found in a ticket, PR or
  comment.

## Known limits (not vulnerabilities)

These are documented behavior; reports about them will be closed with a pointer here.

- `guard.py` reads the command text with a shell tokenizer and never runs it. A script, alias,
  `python -c`, an editor macro or any program that performs the action internally is not seen.
  It stops mistakes and instructions smuggled into tickets, not a determined attacker. The real
  ceiling is a sandbox per agent.
- It covers Claude Code only. Other agents have the rules in `SKILL.md` as text, not a block.
- `permissions.deny` rules for `.env` files cover Claude Code's file tools. Read denial for
  search tools is best effort, per Claude Code's own documentation.
- "One approval per commit" is a rule for the agent in `SKILL.md`; the hook does not track commits.
- `ASF_ALLOW_MAIN_PUSH` deliberately removes the prompt for a Bash call that is only
  `git push origin <refspec>` (or `git merge` on main) in the repos you list, when every push URL
  of `origin` matches and main is written literally. Force pushes, deleting main, expanded forms
  like `@` or `heads/main`, and repos with a custom ssh command, proxy or receive-pack still ask.
  Hooks, credential helpers and `~/.ssh/config` are not inspected (see `docs/guard.md`). Treat the
  list as a trust decision.
- The dashboard trusts every local process and user on the machine: it serves its token to any
  local process. The token and Host/Origin checks protect against websites, not against other
  local users. Do not run it on a shared machine.
- The dashboard shows titles and questions from your agent sessions, which can contain sensitive
  names. Never put it behind a tunnel or publish it.
