# When the model changes

We don't choose when the model changes, and what the old one needed can slow the new one down. Run
this once per model, from any repo. It changes this skill and the global setup, which is what makes
it reach every project. Propose each removal to the human; they decide.

1. **Read** the vendor's release notes and prompting guidance for this model. Quote what you rely on.
2. **Watch it work:** one fast and one full change in a real repo, with invented data. Note where it
   plans twice, loops, or does what an instruction already told it not to bother with.
3. **Cut what it no longer needs,** in this order: `~/.claude/CLAUDE.md`, this skill, always-on
   plugins and hooks, then the repo's `CLAUDE.md`/`AGENTS.md`. Less first; add only after a failure
   you saw.
4. **Never cut for speed:** the Safeguards, the always-full list, the gates, security tests.
5. **Commit** this repo and add a line below.

## Who runs what

Sources: [Eric Risco's video](https://www.youtube.com/watch?v=p6nnqerea7w) (2026-10-23) and the
[ZazenCodes build prompt](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code).
They are the only published recipes per task we found. Neither measured anything; this is a starting
point. Change a row on evidence from our own runs, and record it in the log.

| Task | Default | Risco | Zazen | Note |
|---|---|---|---|---|
| Spec | Opus 5.5 | Opus | Opus | Agree. The agent runs it; the answers and Gate 1 are the human's |
| Build | Opus 5.5 | Opus | Opus | Agree. Claude only until the others have a block |
| Review: code | Sonnet 5.5 | Sonnet | Sonnet | Agree |
| Review: fast lane | Sonnet 5.5, low effort | — | — | Ours; neither has a fast lane with a review |
| Review: security | Opus 5.5, then Sol as a second read | Sol | Opus | Disagree. Sol adds to the review, it doesn't replace it. Note in the PR what each one found |
| Review: UX | Sonnet 5.5 | Sol | Sonnet | Disagree |
| Review: UI | Sonnet 5.5 with `impeccable` | Astra | Sonnet | Disagree. Risco says Astra was trained for UI; OpenAI's Astra page doesn't say so |
| QA and live check | Sonnet 5.5 | — | — | Ours; neither lists them. Runs the app and reports; it doesn't decide the design |
| Risk of the final diff | Opus 5.5 | Opus or Sol | Opus | Agree: a wrong call here is expensive |

Risco's reason for mixing vendors: a model may go easy on its own work. The evidence runs both ways and
excludes security.

How to run them: a Claude subagent takes the `model` directly. Sol runs read-only:
`codex exec -m gpt-6.1-sol --sandbox read-only "<the review>"`.

## Log

| Date | Model | What changed |
|---|---|---|
| 2026-10-30 | Opus 5.5 | Fast lane added. Step 1 done (Anthropic's context-engineering post, OpenAI's Astra post). Step 2 not run yet |
| 2026-10-30 | Sonnet 5.5, GPT-6.1 Sol | Lane test in a scratch repo: a small change to an always-full area (money) was still routed to the fast lane when the skill was not loaded, so the always-full list is stated up front |
| 2026-11-01 | Opus 5.5, Sonnet 5.5, GPT-6.1 Sol | "Who runs what" added from two published recipes. Fresh review also in the fast lane, convergence rules, risk of the final diff, `guard.py`, decisions while building, learned rules in `REVIEW.md` with human approval. Unmeasured |
