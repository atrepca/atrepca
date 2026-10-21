#!/usr/bin/env python3
"""Write recent public GitHub activity between the activity markers in README.md.

Same output format as jamesgeorge007/github-activity-readme, without the Node action.
Uses GITHUB_TOKEN when set (Actions), otherwise the unauthenticated API.
"""
import json
import os
import re
import urllib.request
from pathlib import Path

USER = "atrepca"
MAX_LINES = 5
README = Path(__file__).resolve().parent.parent / "README.md"
START, END = "<!--START_SECTION:activity-->", "<!--END_SECTION:activity-->"


def events():
    req = urllib.request.Request(f"https://api.github.com/users/{USER}/events/public?per_page=100")
    req.add_header("Accept", "application/vnd.github+json")
    if os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def link(text, url):
    return f"[{text}]({url})"


def web(repo, kind, number):
    # The events API now returns trimmed payloads without html_url, so build links ourselves.
    return f"https://github.com/{repo}/{kind}/{number}"


def describe(ev):
    repo = ev["repo"]["name"]
    # Skip this profile repo itself; its own bot commits aren't interesting activity.
    if repo.lower() == f"{USER}/{USER}":
        return None
    repo_link = link(repo, f"https://github.com/{repo}")
    p = ev["payload"]
    if ev["type"] == "IssueCommentEvent":
        i = p["issue"]
        return f"🗣 Commented on {link('#' + str(i['number']), web(repo, 'issues', i['number']))} in {repo_link}"
    if ev["type"] == "IssuesEvent" and p["action"] in ("opened", "closed", "reopened"):
        i = p["issue"]
        emoji = {"opened": "❗️", "closed": "✔️", "reopened": "🔓"}[p["action"]]
        return f"{emoji} {p['action'].capitalize()} issue {link('#' + str(i['number']), web(repo, 'issues', i['number']))} in {repo_link}"
    if ev["type"] == "PullRequestEvent" and p["action"] in ("opened", "closed", "merged"):
        pr = p["pull_request"]
        if p["action"] == "opened":
            emoji, verb = "", "Opened"
        elif p["action"] == "merged" or pr.get("merged"):
            emoji, verb = "🎉", "Merged"
        else:
            emoji, verb = "❌", "Closed"
        return f"{emoji} {verb} PR {link('#' + str(pr['number']), web(repo, 'pull', pr['number']))} in {repo_link}".lstrip()
    if ev["type"] == "ReleaseEvent" and p["action"] == "published":
        rel = p["release"]
        url = rel.get("html_url") or f"https://github.com/{repo}/releases/tag/{rel['tag_name']}"
        return f"✍️ Released {link(rel.get('name') or rel['tag_name'], url)} in {repo_link}"
    return None


def main():
    lines = []
    for ev in events():
        line = describe(ev)
        if line and line not in lines:
            lines.append(line)
        if len(lines) == MAX_LINES:
            break
    body = "\n".join(f"- {l}" for l in lines)
    text = README.read_text()
    new = re.sub(f"{re.escape(START)}.*?{re.escape(END)}", f"{START}\n{body}\n{END}", text, flags=re.S)
    if new != text:
        README.write_text(new)
    print(f"{len(lines)} activity lines")


if __name__ == "__main__":
    main()
