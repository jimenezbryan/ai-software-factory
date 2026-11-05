# How it works

The skill is four Markdown files and a hook:

| File | Role |
|---|---|
| `SKILL.md` | Entry point: the line (steps 0 to 9), the lanes, how to find the step, the safeguards |
| `BUILD.md` | Step 4 (build), the review rules, how the review learns, the fast lane |
| `QA.md` | Step 6 (QA before merge) and step 8 (live check after deploy) |
| `MODELS.md` | Which model runs which task, and what to re-check when the model changes |
| `guard.py` | A Claude Code hook that asks a person before the actions only a person may approve ([guard.md](guard.md)) |

Repo specifics never live in the skill. It reads them from the repo (see [configuration.md](configuration.md)).

## The line

![The line: steps 0 to 9, who does each step, and the two human gates](diagrams/line.svg)

| # | Step | Who | What happens |
|---|---|---|---|
| 0 | Setup | human | No `docs/agents/` yet: the user types `/setup-matt-pocock-skills`. No `checks.md`: it offers to draft one from the manifest |
| 1 | Intake | human | Bugs and requests from others: the user types `/triage` |
| 2 | Shape | human | The user types `/grill-with-docs` (`/grilling` when there is no repo) |
| 3 | Spec | human | The user types `/to-spec`, then `/to-tickets`, and removes or skips the AFK label until Gate 1. Each ticket needs acceptance criteria and a security note. The agent saves the spec and ticket list as a note. **Gate 1:** a human reads them and applies the AFK label |
| 4 | Build | agent | `BUILD.md`. One fresh context per ticket; several ready tickets run one session each, in parallel |
| 5 | Review | agent | A fresh agent that did not build it runs `/code-review`, plus `/security-review` and your own auth-review skill when the security note is yes or the diff touches auth or data. Posted on the PR as a `Review` comment, even when clean |
| 6 | QA | agent | `QA.md` part A. Then **Gate 2:** a human merges |
| 7 | Ship | human | Deploy plus the manual steps in `checks.md`. Agents never deploy |
| 8 | Live check | agent | `QA.md` part B |
| 9 | Record | human | The note is marked done. The agent proposes any learned rule |

Steps 2 and 3 stay in one context. Every build starts fresh from its ticket.

### Finding the step

With a human present, the skill states the step and the evidence for it ("Step 6: PR #14 has a review but no QA checklist") before acting. It reads the input and the tracker; the first match wins. Examples: an open PR with a review but no QA comment naming its last commit is step 6; a ticket with no acceptance criteria, or an AFK label not applied by a maintainer, goes back to step 1 and nothing is built; an AFK-ready, unblocked, unclaimed ticket is built without asking (this is how an orchestrator dispatches work).

### Ticket states

![Ticket label states](diagrams/ticket.svg)

A ticket is claimed by swapping the AFK-ready label for the claimed label. When the agent is stuck it takes the escape hatch: a comment with what it tried and the evidence, claimed swapped for human-ready, stop.

## Lanes

![Lane choice: Answer, Fast or Full](diagrams/lanes.svg)

| Lane | When | What |
|---|---|---|
| Answer | A question; nothing to change | Answer. No branch, no PR |
| Fast | The request authorizes a change and leaves nothing open for the human to decide | No ticket, one PR. Skips the claim and the QA checklist; keeps one fresh low-effort review and one full verify. A note is written before the first change |
| Full | Open decisions that depend on each other, or anything on the always-full list | The line, from step 2 |

Size never picks the lane. **Always full, however small the diff:** money (prices, rates, invoices, payments, pay), auth, sessions or roles, data access rules, migrations or schema, secrets, client or patient data. A fast change that hits a decision it may not make, or reaches that list, stops and moves to full; its note becomes the input to the spec, so nothing done is thrown away. The human can ask for the other lane.

## Notes: the work's memory

A change's intent must survive a dead session, so it lives in a file outside the code, named `YYYY-MM-DD-<slug>.md`. The skill takes the location from your house rules (`CLAUDE.md` / `AGENTS.md`) or your global `~/.claude/CLAUDE.md`. If nothing is configured, or the sandbox cannot write there, it opens a draft PR first and keeps the note in the PR body, and says so. A fast-lane note has five sections: Intent, Scope, Checklist, Evidence, Next. A task is checked off on observed proof, never on belief.

## Build

`BUILD.md` in order: read the house rules, docs and ticket; check the ticket is yours (AFK label from a maintainer, unblocked, has acceptance criteria) and claim it; branch; build test-first; security tests (anonymous denied, wrong role denied, no cross-user access, hostile input, no secrets exposed) when the ticket or diff calls for them; verify by running every command in `checks.md`; open a PR whose body has What changed, How it was verified, Security tests, How to revert, Flags. Three failed fix rounds end in the escape hatch.

## Review and learning

The reviewer is a fresh context given the diff, the ticket or note and the repo's rules, not the builder's reasoning. To converge: at most 3 rounds; after the first, review only what the last fixes changed; name the class of problem; a problem surviving two rounds ends the loop early. The builder rates the **risk of the final diff** (low: something looks wrong; medium: something stops working; high: someone loses money, is locked out or sees another person's data) in the PR's Flags. It tells the human what to read first and never decides the merge.

The review only learns through a person. An agent may propose one rule when a bug got past review or the same problem shows up twice; on a yes it goes into `## Learned rules` in `REVIEW.md` through its own PR. Rules only add checks. No agent removes or loosens a rule, a gate, a safeguard, the always-full list or a test.

## QA

Part A tests the PR's exact head in a fresh worktree (`gh pr checkout <N> --detach`), runs the app locally with invented data, walks each acceptance criterion (happy path, one edge case, the error state, reachability from the normal start screen, phone width for UI, the denied path when the security note is yes), and posts a `QA` comment with `Commit: <SHA>` and `Result: pass` or `fail`. Part B, after the human deploys, confirms the manual steps happened, runs the smoke commands from `checks.md` signed out, and posts a `Live check` comment; if production is broken it opens a new ticket and does not hot-fix.

## Models

`MODELS.md` gives a default model per task (spec, build, code review, fast-lane review, security review, UX and UI review, QA, risk rating) with the sources it was based on, and a procedure to run once per new model: read the release notes, watch it work, cut instructions it no longer needs, never cut the safeguards, gates or security tests. The table is a starting point, not a measurement.
