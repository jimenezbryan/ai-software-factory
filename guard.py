#!/usr/bin/env python3
"""Skill guard: what only a person may approve stops being just text.

Claude Code PreToolUse hook. Merge, push to main, force push, deploy, real migrations, applying the AFK
label and touching .env through Bash all ask for confirmation (Read and Edit of .env are denied by
permissions.deny in settings.json). If you are at the keyboard, you approve in the prompt; if nobody is,
that agent waits on its own and the others keep going.

Exception: ASF_ALLOW_MAIN_PUSH is a comma-separated list of owner/repo (GitHub) or host/owner/repo
(e.g. "acme/notes,git.example.com/team/wiki"). In a repo whose every push URL for origin is listed, a
command that is exactly `git push origin <refspec>...` (or `git merge` on main) does not ask, when each
refspec that reaches main is written `main`, `master` or `<branch>:main|master`. Anything more (other
commands, wrappers, env assignments, git options besides -C, variables, `@`, `heads/main`, a custom ssh
command, proxy or receive-pack) asks. A push whose destination git takes from config (remote.*.push,
push.default=matching or upstream) asks everywhere. Force pushes and deleting main always ask. Unset or empty:
everything asks.

note: reads the command with shlex, never runs it. An alias, a script or `python -c` evades it. It
stops mistakes and instructions hidden in tickets, not a determined attacker. The real ceiling is a
sandbox per agent. It only covers Claude: other agents (Codex, Gemini) need their own block.

Install: in ~/.claude/settings.json under hooks.PreToolUse add a hook with matcher
  Bash|mcp__.*__(deploy_.*|create_deployment|request_promote|request_rollback|assign_alias|start_rolling_release|complete_rolling_release|approve_rolling_release_stage)
and command  python3 "$HOME/.claude/skills/ai-software-factory/guard.py"
Needs Python 3.7+ (stdlib only) and git on PATH.

    python3 guard.py --check   # self-test
"""
import fnmatch, json, os, re, shlex, stat, subprocess, sys, tempfile
from urllib.parse import urlsplit

MAIN = {"main", "master"}
WRAPPERS = {"env", "command", "builtin", "exec", "sudo", "time", "nohup", "nice", "timeout", "xargs", "npx", "bunx", "pnpx"}
KEYWORDS = {"!", "{", "if", "then", "elif", "else", "do", "while", "until"}
ARG_OPTS = {"-u", "-k", "-s", "-n", "-g", "-C", "-I", "-P", "-L", "-p"}  # wrapper options that take a value
SHELLS = {"sh", "bash", "zsh", "dash", "eval"}
SAFE_PUSH_FLAGS = {"-u", "--set-upstream", "-q", "--quiet", "-v", "--verbose", "--progress", "--atomic"}
LITERAL_MAIN = re.compile(r"(?:[\w.-]+(?:/[\w.-]+)*:)?(?:main|master)")  # the only main refspecs the exception takes
# Settings that let git push somewhere other than the URL the guard checked: with any set, no exception.
# GIT_CONFIG makes `git config` read only that file, while push ignores it. GIT_CONFIG_COUNT/KEY_n/VALUE_n and
# GIT_CONFIG_PARAMETERS are not listed: `git config` sees them, so REDIRECT_CONFIG catches what they set (and
# Claude Code's own environment may carry GIT_CONFIG_COUNT for credential prompts).
REDIRECT_ENV = {"GIT_SSH", "GIT_SSH_COMMAND", "GIT_PROXY_COMMAND", "GIT_EXEC_PATH", "GIT_CONFIG"}
REDIRECT_CONFIG = r"^(core\.(sshcommand|gitproxy)|remote\.origin\.(receivepack|vcs|proxy)|http\.(.+\.)?(proxy|sslverify))$"
LABELS_MAX = 20000  # bytes read from the repo's label file
PUNCT = set(";&|()<>")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1([^\n]*)\n(.*?)\n\s*\2\b", re.S)
SUBST = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
ENV_FILE = re.compile(r"(^|/)(\.env(\*|\.[^/]*)?|[^/]*\.env)$")
ENV_SAFE = re.compile(r"\.(example|sample|template|dist|defaults)(\.|$)")
PM = r"(npm|pnpm|yarn|bun)"
DEPLOY = [
    r"vercel\b.* (deploy|promote|rollback|--prod(=true)?)( |$)", r"netlify deploy", r"wrangler\b.* (deploy|publish)( |$)",
    r"(fly|flyctl) deploy", r"railway up", r"firebase deploy", PM + r"\b.* publish( |$)",
    PM + r"\b.*? (deploy|deploy:\S+|\S+:deploy)( |$)", r"supabase\b.* (db push|functions deploy|migration up)",
    r"prisma\b.* (migrate deploy|db push)", r"drizzle-kit (push|migrate)", r"gh workflow run",
]
MCP_DEPLOY = re.compile(r"^mcp__.+__(deploy_\w+|create_deployment|request_promote|request_rollback|assign_alias|"
                        r"start_rolling_release|complete_rolling_release|approve_rolling_release_stage)$")


def git(cwd, *args):
    try:
        return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def repo_id(url):
    """'host/owner/repo' of an https, ssh:// or scp-style (user@host:owner/repo) git URL, else None."""
    url = url.strip().lower()
    if not re.fullmatch(r"[\w.@:/~+-]+", url) or url.count("@") > 1:
        return None
    if "://" in url:
        try:
            p = urlsplit(url)
            host, path = p.hostname, p.path[1:]
        except ValueError:
            return None
        if p.scheme not in ("https", "ssh"):
            return None
    else:
        m = re.fullmatch(r"(?:[^@/:]+@)?([^@/:]+):(.*)", url)
        if not m:
            return None
        host, path = m[1], m[2]
    m = re.fullmatch(r"([\w.-]+)/([\w.-]+?)(?:\.git)?/?", path)
    return f"{host}/{m[1]}/{m[2]}" if host and m else None


def allowed_main_push(cwd):
    """True if every push URL of origin is one of the entries in ASF_ALLOW_MAIN_PUSH."""
    allowed = set()
    for x in os.environ.get("ASF_ALLOW_MAIN_PUSH", "").split(","):
        parts = re.sub(r"\.git$", "", x.strip().strip("/").lower()).split("/")
        parts = ["github.com", *parts] if len(parts) == 2 else parts
        if len(parts) == 3 and all(parts):
            allowed.add("/".join(parts))
    if not allowed or REDIRECT_ENV & set(os.environ):
        return False
    try:  # exit 1 means no such key; anything else (a match, an error) refuses the exception
        if subprocess.run(["git", "-C", cwd, "config", "--get-regexp", REDIRECT_CONFIG],
                          capture_output=True, timeout=5).returncode != 1:
            return False
    except (OSError, subprocess.SubprocessError):
        return False
    # The URLs git will really push to: pushurl, every --add'ed url, insteadOf and pushInsteadOf.
    urls = git(cwd, "remote", "get-url", "--push", "--all", "origin").splitlines()
    return bool(urls) and all(repo_id(u) in allowed for u in urls)


def tokens_of(cmd):
    """Newlines outside quotes separate commands; shlex would treat them as spaces."""
    out, quote, esc = [], None, False
    for ch in cmd:
        if esc:
            esc = False
        elif ch == "\\" and quote != "'":
            esc = True
        elif quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "\n":
            ch = ";"
        out.append(ch)
    lex = shlex.shlex("".join(out), posix=True, punctuation_chars=True)
    lex.whitespace_split, lex.commenters = True, ""
    return list(lex)


def segments(tokens):
    seg = []
    for t in tokens:
        if t and set(t) <= PUNCT:
            if seg:
                yield seg
            seg = []
        else:
            seg.append(t)
    if seg:
        yield seg


def strip_prefix(seg):
    seg = list(seg)
    changed = True
    while seg and changed:
        changed = False
        while seg and (seg[0] in KEYWORDS or re.match(r"^[A-Za-z_]\w*=", seg[0])):
            seg.pop(0)
            changed = True
        if seg and os.path.basename(seg[0]) in WRAPPERS:
            seg.pop(0)
            while seg and (seg[0].startswith("-") or re.match(r"^[\d.]+[smhd]?$", seg[0]) or re.match(r"^[A-Za-z_]\w*=", seg[0])):
                opt = seg.pop(0)
                if opt in ARG_OPTS and seg:
                    seg.pop(0)
            changed = True
        elif len(seg) > 1 and seg[0] in ("npm", "pnpm", "yarn", "bun") and seg[1] in ("exec", "dlx", "x"):
            del seg[:2]
            while seg and (seg[0].startswith("-")):
                seg.pop(0)
            changed = True
    return seg


def target(ref, cwd):
    """What a refspec (or a --delete name) updates on the remote, None if it cannot be told.

    git expands names: `@` is HEAD, HEAD is the current branch, and `heads/main`, `refs/heads/main` or a
    source-only `heads/main` all land on refs/heads/main. So the caller judges the last path component.
    """
    name = ref.lstrip("+").split(":")[-1]
    if name.lower() in ("@", "head"):  # case-insensitive filesystems resolve `head` too
        name = git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
        if name in ("HEAD", ""):
            return None
    return None if re.search(r"@\{|[~^]", name) else name


def upstream_of(ref, cwd):
    """With push.default=upstream, git sends a source-only refspec to that branch's upstream, not its name."""
    if ":" in ref or git(cwd, "config", "push.default").lower() not in ("upstream", "tracking"):
        return ""
    src = target(ref, cwd) or ""
    return git(cwd, "rev-parse", "--abbrev-ref", f"{src}@{{upstream}}") if src else ""


def check_push(args, cwd, plain=False):
    flags = [a for a in args if a.startswith("-")]
    pos = [a for a in args if not a.startswith("-")]
    short = "".join(f[1:] for f in flags if not f.startswith("--"))
    if ("n" in short or "--dry-run" in flags) and "--no-dry-run" not in flags:
        return None
    if "f" in short or any(f in ("--force", "--mirror", "--all") or f.startswith("--force-") for f in flags) \
            or any(p.startswith("+") or p == ":" or "*" in p for p in pos[1:]):
        return "forced or bulk push: rewrites history"
    deleting = "d" in short or "--delete" in flags
    # The exception: only `git push origin <literal refspec>...`, nothing that could change where git pushes.
    plain = plain and pos[:1] == ["origin"] and pos[1:] and set(flags) <= SAFE_PUSH_FLAGS
    # Settings that make git choose the destination itself, whatever the refspec says.
    if git(cwd, "config", "--get-regexp", r"^remote\..*\.push$"):
        return "push in a repo with remote.*.push set: git maps the refspec itself"
    if not pos[1:] and git(cwd, "config", "push.default").lower() == "matching":
        return "push with push.default=matching: pushes every branch, main included"
    for ref in pos[1:] or ["HEAD"]:
        dest = target(ref, cwd)
        if dest is None:
            return "push from a branch that cannot be identified"
        up = upstream_of(ref, cwd)
        if up.rsplit("/", 1)[-1].lower() in MAIN:
            return f"push to {up} (push.default=upstream)"
        # ponytail: any name ending in /main or /master asks (feature/main too), cheaper than modeling git's DWIM.
        if dest.rsplit("/", 1)[-1].lower() not in MAIN:
            continue
        if deleting or ref.startswith(":"):
            return "deletes main"
        if not (plain and LITERAL_MAIN.fullmatch(ref) and allowed_main_push(cwd)):
            return f"push to {dest}"
    return None


def check_git(seg, cwd, plain=False):
    """plain: the segment is the whole command, starts with a literal `git` and has nothing stripped."""
    i = 1
    while i < len(seg) and seg[i].startswith("-"):
        if seg[i] == "-C" and i + 1 < len(seg):
            cwd = os.path.join(cwd, os.path.expanduser(seg[i + 1]))
            i += 2
        elif seg[i] in ("-c", "--git-dir", "--work-tree", "--namespace"):
            plain = False
            i += 2
        else:
            plain = False  # --git-dir=, --exec-path, --bare, --config-env...: git may act elsewhere
            i += 1
    sub, args = (seg[i], seg[i + 1:]) if i < len(seg) else ("", [])
    if sub == "push":
        return check_push(args, cwd, plain)
    if sub == "merge" and not ({"--abort", "--quit", "--ff-only"} & set(args)) \
            and git(cwd, "rev-parse", "--abbrev-ref", "HEAD") in MAIN and not (plain and allowed_main_push(cwd)):
        return "merge into main"
    return None


def afk_labels(cwd, doc="docs/agents/triage-labels.md"):
    """ready-for-agent, plus the name this repo gives it in its label table.

    None if the file exists but is not a plain readable file (a symlink, a device, a FIFO): the repo is
    cloned, so it is untrusted, and the caller then asks for any label. Reads at most LABELS_MAX bytes.
    """
    labels = {"ready-for-agent"}
    path = os.path.join(git(cwd, "rev-parse", "--show-toplevel") or cwd, doc)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return None
            text = os.read(fd, LABELS_MAX).decode("utf-8", "replace")
        finally:
            os.close(fd)
    except FileNotFoundError:
        return labels
    except (OSError, ValueError):
        return None
    return labels | set(re.findall(r"\|\s*`ready-for-agent`\s*\|\s*`([^`]+)`", text))


def applies_afk(cmd, cwd):
    """An agent uses the person's account: its AFK label would look like a Gate 1 approval.

    note: reads the raw text because $(...), <(...) and redirections split the tokens. When in doubt
    it asks: a description containing "--label ready-for-agent" also asks. A variable ($L) or a
    script evades it, like the rest of the guard. Returns the reason to ask, or None.
    """
    if not re.search(r"\b(gh|glab)\b", cmd):
        return None
    cmd = re.sub(r"\\\n\s*", " ", cmd)
    labels = afk_labels(cwd)
    why = "AFK label on a ticket: it is the Gate 1 approval" if labels is not None \
        else "a label on a ticket, and this repo's label file is not a plain readable file"
    afk = "(?:" + "|".join(map(re.escape, labels)) + r")(?![\w-])" if labels is not None else r"[^\s'\",]+"
    value = r"[=\s'\"]*(?:[^\s'\",]*,)*" + afk
    for pattern in (r"--add-label" + value,
                    r"\blabel\s+edit\b.*--name" + value,
                    r"\b(?:issue|pr|mr)\s+(?:create|update|edit)\b.*(?:--label|(?<!\S)-l)" + value,
                    r"/label\s+[~\"']*" + afk):
        if re.search(pattern, cmd, re.I | re.S):
            return why
    if not re.search(r"\b(gh|glab)\s+api\b", cmd) or ("graphql" in cmd and "mutation" not in cmd):
        return None
    method = re.search(r"(?:(?<!\S)-X\s*|--method[=\s]+)['\"]?(\w+)", cmd)
    writes = method[1].upper() not in ("GET", "DELETE") if method \
        else re.search(r"(?<!\S)(-f|-F|--field|--raw-field|--input)", cmd)
    hit = writes and (re.search(afk, cmd, re.I) or re.search(r"addLabelsToLabelable|labelIds", cmd)
                      or re.search(r"/labels\b.*--input|--input.*/labels\b", cmd, re.S))
    return why if hit else None


def check_command(cmd, cwd, depth=0):
    if depth > 4:
        return "command too nested to read"
    # A heredoc body is text (commit messages, files), unless a shell receives it or its delimiter is
    # unquoted: then the shell does execute whatever is in $(...).
    for body in re.findall(r"\b(?:sh|bash|zsh|dash)\s+<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n(.*?)\n\s*\1\b", cmd, re.S):
        why = check_command(body[1], cwd, depth + 1)
        if why:
            return why
    for m in HEREDOC.finditer(cmd):
        if not m.group(1):
            for inner in SUBST.findall(m.group(4)):
                why = check_command(inner[0] or inner[1], cwd, depth + 1)
                if why:
                    return why
    cmd = HEREDOC.sub(lambda m: m.group(3), cmd)
    why = applies_afk(cmd, cwd)
    if why:
        return why
    try:
        tokens = tokens_of(cmd)
    except ValueError:
        return "command that could not be parsed" if re.search(r"\b(push|merge|deploy)\b|\.env", cmd) else None
    for t in tokens:
        base = os.path.basename(t)
        globbed = base.startswith(".") and set(base) & set("*?[") and fnmatch.fnmatch(".env", base)
        if (ENV_FILE.search(t) and not ENV_SAFE.search(t)) or globbed:
            return f"touches a secrets file ({base})"
    # On the raw text: shlex splits backticks into several tokens.
    for inner in SUBST.findall(cmd):
        why = check_command(inner[0] or inner[1], cwd, depth + 1)
        if why:
            return why
    segs = list(segments(tokens))
    # Only a lone, literal command may use the ASF_ALLOW_MAIN_PUSH exception: an earlier command in the
    # same call could change the remote, and $x, globs or braces could expand into other arguments.
    solo = depth == 0 and len(segs) == 1 and not re.search(r"[$`*?\[{]", cmd)
    for raw in segs:
        seg = strip_prefix(raw)
        if not seg:
            continue
        name = os.path.basename(seg[0]).split("@")[0]
        if name == "cd" and len(seg) > 1:
            cwd = os.path.join(cwd, os.path.expanduser(seg[1]))
            continue
        if name in SHELLS:
            code = seg[seg.index("-c") + 1] if "-c" in seg[:-1] else " ".join(seg[1:]) if name == "eval" else ""
            why = check_command(code, cwd, depth + 1) if code else None
        elif name == "git":
            why = check_git(seg, cwd, solo and seg == raw and raw[0] == "git")
        elif name == "gh" and any(seg[i:i + 2] == ["pr", "merge"] for i in range(len(seg))):
            why = "merge of a PR"
        elif name == "gh" and seg[1:2] == ["api"] and any(re.search(r"pulls/\d+/merge", a) for a in seg):
            why = "merge of a PR"
        else:
            line = " ".join([name, *[a for a in seg[1:] if a != "--"]])
            bare_vercel = name == "vercel" and all(a.startswith("-") for a in seg[1:])  # no subcommand: it deploys
            hit = "--dry-run" not in seg and (bare_vercel or any(re.search(r"^" + p, line) for p in DEPLOY))
            why = "deploy or real migration" if hit else None
        if why:
            return why
    return None


def decide(event):
    tool, data = event.get("tool_name", ""), event.get("tool_input") or {}
    if tool == "Bash":
        return check_command(data.get("command") or "", event.get("cwd") or os.getcwd())
    return "deploy" if MCP_DEPLOY.match(tool) else None


def check():
    run = lambda *a, cwd: subprocess.run(a, cwd=cwd, check=True, capture_output=True)
    with tempfile.TemporaryDirectory() as tmp:
        # Self-test only: your own ~/.gitconfig or GIT_SSH* would turn the exception off and fail the cases.
        os.environ.update(HOME=tmp, XDG_CONFIG_HOME=tmp)
        for k in REDIRECT_ENV:
            os.environ.pop(k, None)
        repo, other = os.path.join(tmp, "repo"), os.path.join(tmp, "notes")
        for path, url in ((repo, "https://github.com/x/app.git"), (other, "https://github.com/Example/Notes.git")):
            os.mkdir(path)
            run("git", "init", "-q", "-b", "main", cwd=path)
            run("git", "remote", "add", "origin", url, cwd=path)
            run("git", "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "x", cwd=path)
        feature = os.path.join(tmp, "feat")
        run("git", "worktree", "add", "-q", "-b", "feature", feature, cwd=repo)

        def d(cmd, cwd=repo):
            return decide({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd})

        stop = ["git push origin main", "git push origin master", "git push", "git push -u origin HEAD",
                "git push origin feature:main", "git push origin refs/heads/main", "git -C . push origin main",
                "git -c a=b push origin main", "/usr/bin/git push origin main", "FOO=1 git push origin main",
                "env A=1 git push origin main", "timeout 30 git push origin main", "ls\ngit push origin main",
                "ls && git push origin main", "ls | xargs git push origin main", "bash -c 'git push origin main'",
                "sh -c \"ls; git push origin main\"", "eval git push origin main", "echo $(git push origin main)",
                'echo "$(git push origin main)"', "echo `git push origin main`", "git merge feature",
                "git push --force origin feature", "git push -f origin feature", "git push --force-with-lease",
                "git push origin 'refs/heads/*:refs/heads/*'", "git push origin :", "vercel", "vercel --yes", "git push origin +feature", "git push origin :main", "git push --delete origin main", "git push --all", "git push --mirror",
                "gh pr merge 12 --squash", "gh api -X PUT repos/a/b/pulls/3/merge", "vercel --prod", "vercel deploy",
                "npx vercel deploy --prod", "supabase db push", "supabase functions deploy x", "npm run deploy",
                "npm publish", "prisma migrate deploy", "npx prisma migrate deploy", "cat .env", "cat ./.env.local",
                "source .env", ". ./.env.production", "cat /x/.env", "cat ~/.secrets/app.env", "ls .env*",
                "echo a > .env", "grep KEY .env.staging", "cat 'unterminated .env",
                "! git push origin main", "if git push origin main; then ls; fi", "{ git push origin main; }",
                "env -u CI git push origin main", "sudo -u bob git push origin main", "timeout -k 5 30 git push origin main",
                "git push --dry-run --no-dry-run origin main", "git push -vf origin feature", "git push -fu origin feature",
                "git push -uf origin feature", "gh -R a/b pr merge 3", "gh --repo a/b pr merge 3",
                "npx vercel@latest --prod", "pnpm dlx vercel --prod", "npm exec vercel -- --prod", "npm --prefix . run deploy",
                "pnpm --filter web deploy", "npm run --silent deploy", "npm run db:deploy", "wrangler pages deploy dist", "prisma db push",
                "cat .en[v]", "cat .en?", "cat <<EOF\n$(git push origin main)\nEOF", "cat <<EOF > .env\nhello\nEOF",
                "bash <<EOF\ngit push origin main\nEOF", "cat <<EOF\nhello\nEOF\ngit push origin main",
                "cat .env <<EOF\nhello\nEOF",
                # git expands these to refs/heads/main (checked with real pushes): @ is HEAD, heads/ is refs/heads/.
                "git push origin @", "git push origin @:main", "git push origin heads/main", "git push origin HEAD",
                "git push origin feature:heads/main", "git push origin feature:refs/heads/main",
                "git push origin +feature:heads/master", "git push origin heads/feature:main", "git push origin feature:Main",
                "git push origin @{-1}", "git push origin :heads/main", "git push --delete origin refs/heads/master"]
        for c in stop:
            assert d(c), f"should have stopped: {c}"
        for c in ["git push origin :heads/main", "git push --delete origin refs/heads/master"]:
            assert "deletes main" in d(c), f"normalized delete is still a delete: {c}"
        for c in ["gh issue edit 3 --add-label ready-for-agent", "gh issue edit 3 --add-label=ready-for-agent",
                  "gh issue edit 3 --add-label bug,ready-for-agent", "gh -R a/b issue edit 3 --add-label ready-for-agent",
                  "gh issue create -t x -b y -l ready-for-agent", "gh issue create -t x --label ready-for-agent",
                  "gh issue create -t x -b y -lready-for-agent", "gh issue edit 3 --add-label READY-FOR-AGENT",
                  "gh pr edit 3 --add-label ready-for-agent", "gh pr create --label ready-for-agent",
                  "ls && gh issue edit 3 --add-label ready-for-agent", "glab issue update 3 --label ready-for-agent",
                  "gh label edit bug --name ready-for-agent",
                  "gh issue edit $(gh issue list -q .x) --add-label ready-for-agent",
                  "gh issue create -t x -b $(cat f) -l ready-for-agent",
                  "gh issue create --body-file <(echo hi) --label ready-for-agent",
                  "gh issue edit 3 >/dev/null --add-label ready-for-agent",
                  "gh issue edit 3 --add-label \\\n  ready-for-agent", "gh issue edit 3 \\\n--add-label ready-for-agent",
                  "gh issue edit 3 --add-label ready-for-agent # don't ask",
                  "gh issue create -t x -b 'one\ntwo' --label ready-for-agent",
                  "gh api repos/a/b/issues/3/labels -f 'labels[]=ready-for-agent'",
                  "gh api -X POST repos/a/b/issues/$N/labels -f 'labels[]=ready-for-agent'",
                  "gh api -X PATCH repos/a/b/issues/3 -f 'labels[]=ready-for-agent'",
                  "gh api repos/a/b/issues -f title=x -f 'labels[]=ready-for-agent'",
                  "gh api --method=POST repos/a/b/issues/3/labels -f 'labels[]=ready-for-agent'",
                  "gh api repos/a/b/issues/3/labels --input f.json",
                  "gh api graphql -f query='mutation { addLabelsToLabelable(input: {}) { clientMutationId } }'",
                  "gh api graphql -f query='mutation{updateIssue(input:{id:\"I\",labelIds:[\"LA\"]}){clientMutationId}}'",
                  "glab api -X PUT projects/1/issues/3 -f add_labels=ready-for-agent",
                  "glab issue note 3 -m '/label ~ready-for-agent'"]:
            assert d(c) and "label" in d(c), f"should have stopped for the label: {c}"
        for c in ["gh issue list --label ready-for-agent", "gh issue view 3", "gh issue edit 3 --add-label needs-info",
                  "gh issue edit 3 --remove-label ready-for-agent", "gh label create ready-for-agent --color 0e8a16",
                  "gh issue create -t x -b 'without the ready-for-agent label'", "gh api repos/a/b/issues/3/labels",
                  "gh api -X GET repos/a/b/issues/3/labels", "gh pr create --label bug",
                  "gh pr list --search update --label ready-for-agent", "gh issue list -S create -l ready-for-agent",
                  "gh search issues update --label ready-for-agent", "gh api -X POST repos/a/b/issues/3/labels -f 'labels[]=bug'",
                  "gh api -X DELETE repos/a/b/issues/3/labels/ready-for-agent", "glab label create --name ready-for-agent",
                  "gh api graphql -f query='{ repository { labels(query: \"ready-for-agent\") { totalCount } } }'",
                  "gh issue create -t x -b \"$(cat <<'EOF'\ncon --label ready-for-agent\nEOF\n)\"",
                  "gh issue edit 3 --add-label ready-for-agent-later", "cat notes --add-label ready-for-agent"]:
            assert d(c) is None, f"should not have stopped: {c} -> {d(c)}"
        with open(os.path.join(repo, "t.md"), "w") as f:
            f.write("| `ready-for-agent` | `ready` | x |\n")
        assert afk_labels(repo, "t.md") == {"ready-for-agent", "ready"}, "honors the repo label"
        go = ["git status", "git log --oneline", "git add .", "git commit -m 'git push origin main'",
              "git commit -m \"merge .env fix\"", "echo 'git push origin main'", "echo gh pr merge", "git push origin feature",
              "git push -u origin feature", "git push --dry-run origin main", "git pull origin main", "git merge --abort",
              "gh pr view 12", "gh pr create --title x", "gh api repos/a/b", "cat .env.example", "cp .env.sample x",
              "cat environment.ts", "cat src/env.ts", "npm test", "npm run build", "npm run db -- start",
              "supabase start", "supabase db reset", "vercel env ls", "vercel ls", "ls -la", "cat notes.txt",
              "git commit -m \"$(cat <<'EOF'\nabout git push origin main\nEOF\n)\"",
              "git commit -m \"$(cat <<'EOF'\nfix .env and deploy\nEOF\n)\"",
              "python3 - <<'E'\ns = 'cat .env; git push origin main'\nE", "cat <<EOF > notes.txt\nread .env\nEOF",
              "cat <<'EOF'\n$(git push origin main)\nEOF", "git push origin :feature", "git push --delete origin feature",
              "npm run build:deploy-preview", "npm run predeploy", "npm publish --dry-run", "supabase db push --dry-run",
              "vercel env ls --yes", "cat .env.example.bak", "git merge --ff-only origin/main", "cat .gitignore", "ls .*ignore", "cat *"]
        for c in go:
            assert d(c) is None, f"should not have stopped: {c} -> {d(c)}"
        assert d("git push", feature) is None, "push of a normal branch"
        assert d("git push origin HEAD", feature) is None
        assert d("git push origin @", feature) is None and d("git push origin heads/feature", feature) is None
        for c in ["git push origin @:heads/main", "git push origin HEAD:refs/heads/main", "git push origin feature:heads/main"]:
            assert d(c, feature), f"from a branch, still reaches main: {c}"
        assert d("git merge main", feature) is None, "bringing main into a branch"
        # git picks the destination from config (each checked with a real push to a bare repo).
        assert d("git push origin head") and d("git push origin Head:main"), "head is HEAD on macOS"
        assert d("git push origin head", feature) is None
        run("git", "config", "remote.origin.push", "refs/heads/feature:refs/heads/main", cwd=repo)
        for c in ["git push origin feature", "git push origin", "git push"]:
            assert d(c, feature), f"remote.origin.push maps it to main: {c}"
        run("git", "config", "--unset", "remote.origin.push", cwd=repo)
        run("git", "update-ref", "refs/remotes/origin/main", "HEAD", cwd=repo)
        run("git", "config", "branch.feature.remote", "origin", cwd=repo)
        run("git", "config", "branch.feature.merge", "refs/heads/main", cwd=repo)
        assert d("git push origin feature", feature) is None, "push.default=simple keeps the name"
        for mode in ("upstream", "tracking"):
            run("git", "config", "push.default", mode, cwd=repo)
            for c in ["git push", "git push origin", "git push origin feature", "git push origin HEAD"]:
                assert d(c, feature), f"push.default={mode} sends feature to its upstream, main: {c}"
            assert d("git push origin feature:feature", feature) is None, "an explicit destination wins"
        run("git", "config", "push.default", "matching", cwd=repo)
        assert d("git push", feature) and d("git push origin", feature), "matching pushes main too"
        assert d("git push origin feature", feature) is None
        run("git", "config", "--unset", "push.default", cwd=repo)
        run("git", "config", "--remove-section", "branch.feature", cwd=repo)
        assert d("git push", feature) is None, "cleaned up"
        assert d(f"cd {repo} && git push") and d(f"git -C {repo} push"), "cd and -C change repo"
        def with_allow(value, cmd, cwd):
            old = os.environ.pop("ASF_ALLOW_MAIN_PUSH", None)
            if value is not None:
                os.environ["ASF_ALLOW_MAIN_PUSH"] = value
            try:
                return d(cmd, cwd)
            finally:
                os.environ.pop("ASF_ALLOW_MAIN_PUSH", None)
                if old is not None:
                    os.environ["ASF_ALLOW_MAIN_PUSH"] = old

        for unset in (None, "", " , ,"):
            assert with_allow(unset, "git push origin master", other), "no allow-list: everything asks"
        for allow in ("example/notes", " Other/x , EXAMPLE/Notes ,", "example/notes,", "github.com/example/notes.git"):
            assert with_allow(allow, "git push origin master", other) is None, f"allowed repo does not ask: {allow!r}"
            assert with_allow(allow, "git push origin master", repo), "another repo still asks"
        allow = lambda cmd, cwd=other: with_allow("example/notes", cmd, cwd)
        evil = "https://github.com/x/app.git"
        for c in ["git push origin main", "git push -u origin main", "git push origin HEAD:main", "git push origin feature:main",
                  "git push --set-upstream -q origin main", f"git -C {other} push origin main", "git push origin main;",
                  "git merge feature"]:
            assert allow(c, other if "-C" not in c else repo) is None, f"exception should apply: {c}"
        assert d("git merge feature", other), "merge into main asks without the exception"
        for c in ["git push", "git push origin", "git push --force origin master", f"git push {evil} main",
                  f"git -c remote.origin.url={evil} push origin main", f"git -c remote.origin.pushurl={evil} push origin main",
                  f"git --git-dir={repo}/.git push origin main", f"git --git-dir {repo}/.git push origin main",
                  f"GIT_DIR={repo}/.git git push origin main", f"env GIT_DIR={repo}/.git git push origin main",
                  f"git --work-tree={repo} push origin main", "git --exec-path=/x push origin main", f"git -C {repo} push origin main",
                  f"git push --repo={evil} origin main", f"git push --repo origin {evil} main", "git push -o x origin main",
                  "git push origin :main", "git push --delete origin main", "git push origin --delete master",
                  "git push -d origin main", "git push origin :refs/heads/master", f"cd {other} && git push origin main",
                  f"git config remote.origin.pushurl {evil} && git push origin main", "bash -c 'git push origin main'",
                  "timeout 30 git push origin main", "./git push origin main",
                  "git -c a=b merge feature", "ls; git merge feature",
                  # Not a literal main refspec: the exception takes only main, master and <branch>:main|master.
                  "git push origin feature:heads/master", "git push origin feature:refs/heads/main", "git push origin @",
                  "git push origin @:main", "git push origin heads/main", "git push origin refs/heads/master",
                  "git push origin HEAD", "git push origin feature:Main", "git push origin +feature:heads/master"]:
            assert allow(c), f"exception must not apply: {c}"
        # Settings that redirect where an allowed push lands (a real push with core.sshCommand wrote elsewhere).
        for key, value in (("core.sshCommand", "f() { exec git-receive-pack /x.git; }; f"), ("core.gitProxy", "x"),
                           ("remote.origin.receivepack", "x"), ("remote.origin.vcs", "x"), ("remote.origin.proxy", "x"),
                           ("http.proxy", "x"), ("http.https://github.com/.proxy", "x"), ("http.sslVerify", "false")):
            run("git", "config", key, value, cwd=other)
            assert allow("git push origin main") and allow("git merge feature"), f"redirecting setting, must ask: {key}"
            run("git", "config", "--unset", key, cwd=other)
            assert allow("git push origin main") is None, f"cleaned up: {key}"
        for env in ({"GIT_SSH": "x"}, {"GIT_SSH_COMMAND": "x"}, {"GIT_PROXY_COMMAND": "x"}, {"GIT_EXEC_PATH": "x"},
                    {"GIT_CONFIG": os.devnull}, {"GIT_CONFIG_PARAMETERS": "'core.sshcommand=x'"},
                    {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.sshCommand", "GIT_CONFIG_VALUE_0": "x"}):
            saved = {k: os.environ.get(k) for k in env}
            os.environ.update(env)
            try:
                assert allow("git push origin main"), f"redirecting environment, must ask: {env}"
            finally:
                for k, v in saved.items():
                    os.environ.pop(k) if v is None else os.environ.update({k: v})
        os.environ.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="credential.interactive", GIT_CONFIG_VALUE_0="false")
        try:
            assert allow("git push origin main") is None, "harmless env config (as Claude Code sets) keeps the exception"
        finally:
            for k in ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"):
                os.environ.pop(k)
        for c in ["git push origin :main", "git push --delete origin main", "git push origin --delete master"]:
            assert "deletes main" in d(c) and "deletes main" in d(c, other), f"deleting main is its own reason: {c}"
        for setup in (["config", "remote.origin.pushurl", evil], ["remote", "set-url", "--add", "origin", evil],
                      ["config", f"url.{evil}.pushInsteadOf", "https://github.com/Example/Notes.git"],
                      ["config", "url.https://evil.example/.insteadOf", "https://github.com/"],
                      ["config", "remote.pushDefault", "elsewhere"]):
            run("git", *setup, cwd=other)
            if setup[1] != "remote.pushDefault":  # pushDefault only redirects a bare push
                assert allow("git push origin main"), f"git pushes elsewhere, must ask: {setup}"
            assert allow("git push"), f"bare push must ask: {setup}"
            run("git", "remote", "remove", "origin", cwd=other)
            for key in ("url", "remote"):
                subprocess.run(["git", "config", "--remove-section", f"{key}.{evil}"], cwd=other, capture_output=True)
            subprocess.run(["git", "config", "--remove-section", "url.https://evil.example/"], cwd=other, capture_output=True)
            subprocess.run(["git", "config", "--unset", "remote.pushDefault"], cwd=other, capture_output=True)
            run("git", "remote", "add", "origin", "https://github.com/Example/Notes.git", cwd=other)
        assert allow("git push origin main") is None, "setup cleaned up"
        for url in ("https://github.com/example/notes-evil.git", "https://github.com/evil/example/notes.git",
                    "https://github.com/xexample/notes.git", "git@github.com:example/notes/extra.git",
                    "https://evil.example/example/notes.git", "git@evil.example:example/notes.git",
                    "ssh://git@evil.example/example/notes.git", "https://github.com@evil.example/example/notes.git",
                    "http://github.com/example/notes.git", "file:///github.com/example/notes.git", "/tmp/github.com/example/notes"):
            run("git", "remote", "set-url", "origin", url, cwd=other)
            assert allow("git push origin master"), f"look-alike must ask: {url}"
        for url in ("git@github.com:Example/Notes.git", "ssh://git@github.com/example/notes", "https://github.com/example/notes/"):
            run("git", "remote", "set-url", "origin", url, cwd=other)
            assert allow("git push origin master") is None, f"URL form matches: {url}"
        run("git", "remote", "set-url", "--add", "origin", "https://github.com/example/notes.git", cwd=other)
        assert allow("git push origin main") is None, "several push URLs, all listed"
        run("git", "remote", "remove", "origin", cwd=other)
        run("git", "remote", "add", "origin", "ssh://git@git.example.com/team/notes.git", cwd=other)
        assert allow("git push origin main"), "owner/repo means github.com"
        assert with_allow("git.example.com/team/notes", "git push origin main", other) is None, "host/owner/repo"
        linked = os.path.join(tmp, "linked")
        os.makedirs(os.path.join(linked, "docs", "agents"))
        run("git", "init", "-q", cwd=linked)
        try:
            os.symlink(os.devnull, os.path.join(linked, "docs", "agents", "triage-labels.md"))
        except OSError:
            pass  # no symlinks on this system
        else:
            assert afk_labels(linked) is None, "a symlinked label file is not read"
            for c in ["gh issue edit 3 --add-label ready-for-agent", "gh issue edit 3 --add-label ready"]:
                assert "label" in (d(c, linked) or ""), f"unreadable label file: any label asks: {c}"
            assert d("gh issue view 3", linked) is None
        tool = lambda n: decide({"tool_name": n, "tool_input": {}})
        assert tool("mcp__example__deploy_project") and tool("mcp__example__request_promote")
        assert tool("mcp__example__get_deployment") is None and tool("mcp__example__list_deployments") is None
        assert decide({"tool_name": "Read", "tool_input": {}}) is None
    print("ok")


def main():
    if "--check" in sys.argv:
        return check()
    try:
        why = decide(json.load(sys.stdin))
    except Exception as e:  # A broken guard asks; it never lets things through silently.
        why = f"the guard failed ({type(e).__name__})"
    if why:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": f"Only a person approves this: {why}.",
        }}, ))


if __name__ == "__main__":
    main()
