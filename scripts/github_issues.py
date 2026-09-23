#!/usr/bin/env python3
"""Utility script to create and manage GitHub issues for Speed-X."""

import json
import subprocess
import urllib.request
import sys
from typing import List, Optional


def get_github_token() -> Optional[str]:
    try:
        p = subprocess.Popen(
            ["git", "credential", "fill"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        out, _ = p.communicate("protocol=https\nhost=github.com\n\n")
        for line in out.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1]
    except Exception as e:
        print("Could not retrieve token:", e)
    return None


def create_issue(title: str, body: str, labels: Optional[List[str]] = None) -> Optional[dict]:
    token = get_github_token()
    if not token:
        print("No GitHub token available.")
        return None

    data = {
        "title": title,
        "body": body,
        "labels": labels or ["enhancement"],
    }
    req = urllib.request.Request(
        "https://api.github.com/repos/festomanolo/speed-x/issues",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "SpeedX-Automation",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            issue = json.loads(resp.read().decode())
            print(f"Created Issue #{issue['number']}: {issue['title']}")
            return issue
    except Exception as e:
        print(f"Failed to create issue '{title}':", e)
        return None


def close_issue(issue_number: int, comment: Optional[str] = None) -> bool:
    token = get_github_token()
    if not token:
        print("No GitHub token available.")
        return False

    if comment:
        comment_issue(issue_number, comment)

    data = {"state": "closed"}
    req = urllib.request.Request(
        f"https://api.github.com/repos/festomanolo/speed-x/issues/{issue_number}",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "SpeedX-Automation",
        },
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            issue = json.loads(resp.read().decode())
            print(f"Closed Issue #{issue['number']}: {issue['title']}")
            return True
    except Exception as e:
        print(f"Failed to close issue #{issue_number}:", e)
        return False


def comment_issue(issue_number: int, body: str) -> bool:
    token = get_github_token()
    if not token:
        print("No GitHub token available.")
        return False

    data = {"body": body}
    req = urllib.request.Request(
        f"https://api.github.com/repos/festomanolo/speed-x/issues/{issue_number}/comments",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "SpeedX-Automation",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Added comment to Issue #{issue_number}")
            return True
    except Exception as e:
        print(f"Failed to comment on issue #{issue_number}:", e)
        return False


def list_issues(state: str = "open"):
    token = get_github_token()
    if not token:
        print("No GitHub token available.")
        return

    req = urllib.request.Request(
        f"https://api.github.com/repos/festomanolo/speed-x/issues?state={state}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SpeedX-Automation",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            issues = json.loads(resp.read().decode())
            for i in issues:
                print(f"#{i['number']} [{i['state']}] {i['title']}")
    except Exception as e:
        print("Failed to list issues:", e)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "create" and len(sys.argv) > 3:
            title = sys.argv[2]
            body = sys.argv[3]
            labels = sys.argv[4].split(",") if len(sys.argv) > 4 else None
            create_issue(title, body, labels)
        elif cmd == "close" and len(sys.argv) > 2:
            num = int(sys.argv[2])
            comment = sys.argv[3] if len(sys.argv) > 3 else None
            close_issue(num, comment)
        elif cmd == "comment" and len(sys.argv) > 3:
            num = int(sys.argv[2])
            comment = sys.argv[3]
            comment_issue(num, comment)
        elif cmd == "list":
            state = sys.argv[2] if len(sys.argv) > 2 else "open"
            list_issues(state)
        elif len(sys.argv) > 2:
            # Fallback legacy syntax: python3 scripts/github_issues.py <title> <body> [labels]
            title = sys.argv[1]
            body = sys.argv[2]
            labels = sys.argv[3].split(",") if len(sys.argv) > 3 else None
            create_issue(title, body, labels)
        else:
            print("Usage: python3 scripts/github_issues.py [create|close|comment|list] ...")
    else:
        print("Usage: python3 scripts/github_issues.py [create|close|comment|list] ...")
