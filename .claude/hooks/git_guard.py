#!/usr/bin/env python3
"""Team rules for git, run by Claude Code before every Bash command (see .claude/settings.json).

Blocks (exit 2, reason goes back to Claude):
  1. a commit or push that carries AI attribution (Co-Authored-By: Claude, noreply@anthropic.com, ...);
  2. a force-push (history is shared; see CLAUDE.md rule 4);
  3. a commit that changes files but not .claude/context/ (CLAUDE.md rule 2), unless the message has
     "[skip context]".
Anything else, or any error inside this script, lets the command run.
"""
import json
import re
import subprocess
import sys

AI_MARK = re.compile(r"co-authored-by:\s*claude|noreply@anthropic\.com|generated with \[?claude", re.I)
_OPTS = r"\bgit\s+(?:-C\s+(?:\"[^\"]*\"|'[^']*'|\S+)\s+|-c\s+\S+\s+|--\S+\s+)*"
GIT_COMMIT = re.compile(_OPTS + r"commit(?=\s|$)")
GIT_PUSH = re.compile(_OPTS + r"push(?=\s|$)")
FORCE = re.compile(r"(\s--force(?!-with-lease)\b|\s-[a-zA-Z]*f[a-zA-Z]*\b|\s\+[\w/.-]+(:|\s|$))")
CONTEXT = (".claude/context/", "CLAUDE.md")


def git(cwd, *args):
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=20)
    return out.stdout if out.returncode == 0 else ""


def block(reason):
    print(reason, file=sys.stderr)
    sys.exit(2)


def main():
    data = json.load(sys.stdin)
    cmd = (data.get("tool_input") or {}).get("command") or ""
    cwd = data.get("cwd") or "."
    is_commit, is_push = bool(GIT_COMMIT.search(cmd)), bool(GIT_PUSH.search(cmd))
    if not (is_commit or is_push):
        return

    if AI_MARK.search(cmd):
        block("Team rule (CLAUDE.md rule 3): no AI attribution in commits. Remove the Co-Authored-By / "
              "'Generated with' line and run the command again.")

    if is_push:
        push_part = cmd[GIT_PUSH.search(cmd).start():]
        if FORCE.search(push_part.split("&&")[0].split(";")[0]):
            block("Team rule (CLAUDE.md rule 4): no force-push; teammates share this history. Use "
                  "`git pull --rebase` and a normal push. A history rewrite needs the whole team's "
                  "agreement and then only `--force-with-lease`.")
        unpushed = git(cwd, "log", "--format=%B", "--branches", "--not", "--remotes=origin")
        if AI_MARK.search(unpushed):
            block("Team rule (CLAUDE.md rule 3): some local commits that are not on GitHub carry AI "
                  "attribution (often old history pulled back in by a merge). Do not push them. Run "
                  "`git log --branches --not --remotes=origin` to see them; usually `git reset --hard "
                  "origin/<branch>` after saving your own changes, or `git pull --rebase`, fixes it.")

    if is_commit and "[skip context]" not in cmd and "--amend" not in cmd:
        changed = [line[3:].strip().strip('"') for line in git(cwd, "status", "--porcelain").splitlines()]
        changed = [p.split(" -> ")[-1] for p in changed if p]
        if changed and not any(p.startswith(CONTEXT) for p in changed) \
                and not any(c in cmd for c in CONTEXT):
            block("Team rule (CLAUDE.md rule 2): this commit does not update the shared context. Add an "
                  "entry at the top of .claude/context/SESSIONS.md and fix anything now wrong in "
                  ".claude/context/STATE.md, stage them, then commit. Trivial commit (typo)? Put "
                  "[skip context] in the message.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # never stop work because the guard itself broke
        sys.exit(0)
