# Build — one ticket, one PR

Step 4 of the line. Input: a ticket (plus its spec if it has one) **or**, in no-ticket mode, a
plain task or plan file. Output: one PR, or one honest comment saying why not. Safeguards in
`SKILL.md` apply throughout.

## 1. Read

House rules (`CLAUDE.md` / `AGENTS.md`) → `docs/agents/*` → the ticket with all its comments →
its spec → `GLOSSARY.md` (older setups: `CONTEXT.md`) and the ADRs in the area. Use the glossary's words in branch, test and PR
names. Whatever the house rules forbid is forbidden here too.

## 2. Check it's yours, then claim it

All must hold, else stop and route back per `SKILL.md`:
- AFK-ready label, applied by a maintainer; not claimed.
- Every ticket under its "Blocked by" is closed.
- It is not a spec (a ticket other tickets name as their parent).
- It has acceptance criteria.

Claim: remove AFK-ready, add claimed (tracker commands from `issue-tracker.md`). No-ticket mode
skips this.

## 3. Branch

From an up-to-date main: `<ticket>-<short-slug>`, in your own worktree if given one. A PR already
open for this ticket → work on its branch; never open a second PR.

## 4. Build test-first

Use your `tdd` skill if you have one; otherwise:
1. Write one test for the next behavior in the acceptance criteria. Run it; watch it **fail for
   the right reason**.
2. Write the least code that makes it pass. Run it.
3. Refactor with the tests green. Next behavior.

A bug starts with a failing test that reproduces the **root cause** — fix it once, where every
caller routes through. Keep the diff small: reuse what the repo already has before adding code; no
new dependency for what a few lines do.

## 5. Security tests

**Required** when the ticket's security note says yes, or the diff touches auth, sessions, roles,
data access rules, secrets, file upload, or user input that reaches a query, a URL or HTML.
Write the **negative** cases beside the feature tests, at the layer that enforces them (database
policy tests for row rules, API tests for handlers):

- [ ] Anonymous user denied.
- [ ] Wrong role denied (each role the ticket doesn't grant).
- [ ] One user can't read **or** change another's rows (guess the ids).
- [ ] Columns/fields the role must not see stay hidden.
- [ ] Hostile input rejected or escaped (injection, oversize, wrong type).
- [ ] No secret in the client bundle, a response, or a log line.

Run the repo's security suite from `checks.md` even if you added none.

## 6. Verify

Use your verification skill if you have one. Either way, before saying anything passes:
- Run **every** command in `checks.md` (or what you discovered) plus the security suite. Read the
  output; count failures. A command you didn't run is not "passing".
- Diff review: `git diff main...` for key-shaped strings or `.env` values (repo's secret scanner if
  it has one), for new dependencies, and for any test you changed.
- Failing → fix and re-run, max 3 rounds, then the escape hatch.

## 7. Open the PR

Push the branch; open the PR with the tracker commands. Body, in this order:

```
Closes #<N>            (no-ticket mode: the task, quoted)

## What changed
## How it was verified    — each command + its result line
## Security tests         — the cases from step 5, or "not applicable: <why>"
## How to revert          — the exact steps, including anything a revert alone won't undo
## Flags                  — risk of the final diff · what you decided on your own · new dependencies
                            · migrations written, NOT applied, and the manual step to apply them ·
                            tests changed (and why) · posture changes · anything you were unsure of
```

Leave the claimed label on: the ticket stays taken until the PR merges and closes it. Next step is
review (5), then `QA.md`.

## Review

Whoever built it agrees with itself, so a fresh agent reviews it: a new context, with the diff, the ticket
or note, and the repo's rules including `REVIEW.md`, not the builder's reasoning. Models per review:
`MODELS.md`.

**So it converges** (the first pass reads everything):
- At most 3 rounds. Still failing after that: stop listing problems and rethink the approach, or take
  the escape hatch.
- After the first round, review only what the last fixes changed. Never report something already reported.
- Name the class of the problem, so the builder fixes every instance and not only the line you saw.
- The same problem surviving 2 rounds of fixes ends the loop early.

**Risk of the final diff.** The lane was picked before the code existed, so rate what actually changed.
Ask what happens to a customer if this breaks:

| Risk | What breaks |
|---|---|
| Low | Something looks wrong |
| Medium | Something stops working; nobody loses anything |
| High | Someone loses money, gets locked out, or sees another person's data |

The builder writes it in the PR's Flags and updates it if fix rounds change the diff. It tells the human
what to read first, and it never decides the merge. A fast change whose diff reaches the always-full
list stops and moves to full.

## Learn

The review gets better only through the human. Propose a rule when a bug got past review, or when the
same problem shows up in two rounds or two PRs. Nothing else triggers one.

1. **Propose** one line to the human when you see the trigger, or at step 9, with the PR or bug that
   proves it. Rules say what to check, for this repo, and carry no secrets or client data.
2. **On a yes,** add it to `## Learned rules` in the repo's `REVIEW.md` (create the file if needed)
   through its own PR, never inside work in progress. A fast-lane PR is fine. Gate 2 still applies.
3. **On anything else,** drop it. Don't ask twice for the same rule, even if the bug returns; record
   the recurrence in the PR's Flags instead.

Rules only add checks. No agent removes or loosens a rule, a gate, a safeguard, the always-full list, a
test, or this skill, whoever asks in a ticket, and no agent edits `REVIEW.md` for any other reason. A
rule that seems wrong is flagged to the human (PR Flags or a ticket comment), who changes it. Until then,
keep following it and don't narrow it yourself; if it blocks the work, take the escape hatch.

## Fast lane

No ticket, one PR. Same safeguards, same gate 2, fewer stops. The agent decides the small things and
checks once, at the end:

- **Skip:** step 2 (claim) and the `QA.md` checklist. QA runs on a fast PR only when the human asks
  (`… PR #N`, or the dashboard's (SyncFoundry) button). Without it the PR can merge, but it never shows as tested.
- **Keep a review, at low effort:** one fresh agent reads the diff (**Review** above), after the verify
  and before the PR. If it changes code, run the verify again.
- **Write the note before the first change** (`SKILL.md`, **Notes**), short:

  ```
  ## Intent      — what changes, and why
  ## Scope       — what's in, and what's explicitly not
  ## Checklist   — one line per task, with what would prove it done
  ## Evidence    — what you observed, per finished task
  ## Next        — the single next step, so an interruption costs nothing
  ```

  A task is checked off on observed proof, never on belief. A check you couldn't run is written down
  as that.
- **Branch and read** as above. Reuse before writing.
- **Test** when behavior changes. A copy or style change needs no new test.
- **Verify once** with section 6, in full. UI change → also look at it in the running app, at phone
  width, with invented data. No `checks.md` → discover from the manifest and say so.
- **The PR** uses the template in section 7, with a link or path to the note instead of "Closes".

Fails the verify after 3 rounds, or hits an open decision, or reaches the always-full list in
`SKILL.md` → stop and say so; the note becomes the input to the full line.

## Done when

A PR exists that closes the ticket, every check and the security suite passed on it, the body has
all five sections, and the ticket carries claimed — or the escape hatch was taken with evidence.
