# QA — does it work for a user?

Review (step 5) asks "is the code right?". QA asks "does the running app do what the ticket
promised, for the people it promised it to?". Green tests are not QA. Safeguards in `SKILL.md`
apply throughout.

## A. Before merge (step 6)

1. **Test the PR's exact head.** In a fresh worktree: `gh pr checkout <N> --detach`, then note
   `git rev-parse HEAD`. That SHA goes in your comment.
2. **Run the app locally with invented data**, the way `checks.md` says (its seed, its test
   users). Never production, never real client data. Can't run it → say so in the PR and hand QA
   to the human; don't mark it passed.
3. **Turn each acceptance criterion into checklist lines** and walk them in the running app, as
   the role the criterion names:
   - [ ] Happy path.
   - [ ] One edge case (empty, very long, zero, the boundary the criterion implies).
   - [ ] The error state (network or permission failure shows a message, not a blank or a crash).
   - [ ] **Reachable:** a user can get there by tapping from the normal start screen. A feature
         with no path to it is not done.
   - [ ] UI change → also at phone width.
   - [ ] Security note yes → the **denied** path in the UI too: sign in as the role that must not
         see it, and look.
4. **Post the evidence on the PR** as a comment headed `QA`, with a line `Commit: <SHA>`, a line
   `Result: pass` or `Result: fail`, and the checklist with ✅/❌ per line, screenshots (or the
   command and output for non-UI work). It counts only with the PR's last commit and `Result: pass`
   and no ❌. A new commit needs a new QA; on the same commit, the latest comment wins.
5. All ✅ → tell the human it's ready for gate 2. Any ❌ → `Result: fail` and stop: QA doesn't fix.
   The fix goes through `BUILD.md` on the PR's branch, by whoever holds that branch (same 3-round
   cap). Then QA again, on the new commit.

## B. After deploy (step 8)

The human deploys and runs the manual steps. Then:

1. **Confirm the manual steps happened** — ask the human, or check read-only (e.g. the migration
   shows as applied). "Pushed" is not "live": a push may not run migrations or deploy functions.
2. **Smoke check** with the commands in `checks.md`: load the smoke URL(s) signed out, run the
   repo's post-deploy check script, read the error log for the minutes since deploy. Do not sign
   in as a real user; signed-in checks in production are the human's.
3. **Report** on the merged PR: `Live check` + each command and result.
4. Broken in production → open a **new ticket** with the evidence and tell the human. No hot-fix,
   no revert on your own.

## Done when

Part A: a `QA` comment on the PR naming its last commit, with every acceptance criterion walked and
evidenced. Part B: a
`Live check` comment on the merged PR, or a new ticket describing what is broken.
