import sys
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(__file__).parent / "log.txt"
TOOL = "Claude (claude.ai web chat) + VS Code"
MODEL = "claude-opus-5-5"
CONTEXT = f"""Context:
tool={TOOL}
model={MODEL}
branch=main
repo_root={Path(__file__).parent.resolve()}
worktree=main
parent_agent=none
"""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def start():
    LOG.open("a", encoding="utf-8").write(
        f"## [{now()}] SESSION START\n\ntool={TOOL}\nmodel={MODEL}\n"
        f"Repo Root: {Path(__file__).parent.resolve()}\nBranch: main\nWorktree: main\n"
        f"Parent Agent: none\nLanguage: py\nTime Remaining: not configured\n\n")


def turn(title, prompt, summary, actions):
    acts = "\n".join(f"* {a}" for a in actions)
    LOG.open("a", encoding="utf-8").write(
        f"## [{now()}] {title[:80]}\n\nUser Prompt (verbatim, secrets redacted):\n{prompt}\n\n"
        f"Agent Response Summary:\n{summary}\n\nActions:\n{acts}\n\n{CONTEXT}\n")


if __name__ == "__main__":
    if sys.argv[1:] == ["start"]:
        start()
    else:
        title = input("Title: ")
        prompt = input("Your prompt (paste): ")
        summary = input("What was done (2-5 sentences): ")
        actions = input("Actions, separated by ; : ").split(";")
        turn(title, prompt, summary, [a.strip() for a in actions if a.strip()])