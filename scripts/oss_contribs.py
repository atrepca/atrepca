#!/usr/bin/env python3
"""Build docs/oss.json and the README timeline SVGs from merged upstream PRs.

Uses GITHUB_TOKEN when set (Actions), otherwise the unauthenticated API.
Area labels and the legacy flag are curated in data/areas.json.
"""
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from html import escape
from pathlib import Path

USER = "atrepca"
ROOT = Path(__file__).resolve().parent.parent
AREAS = json.loads((ROOT / "data" / "areas.json").read_text())
# URLs to leave off the timeline (test PRs and the like).
EXCLUDE = set(json.loads((ROOT / "data" / "exclude.json").read_text()))
TOKEN = os.environ.get("GITHUB_TOKEN")


def api(path):
    req = urllib.request.Request(f"https://api.github.com{path}")
    req.add_header("Accept", "application/vnd.github+json")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < 4:
                time.sleep(30 * (attempt + 1))
                continue
            raise


def search_prs(q):
    """All upstream PRs matching q, skipping repos owned by USER."""
    found, page = [], 1
    while True:
        path = f"/search/issues?q={urllib.parse.quote(q)}&per_page=100&page={page}"
        for _ in range(3):
            res = api(path)
            if not res.get("incomplete_results"):
                break
            time.sleep(10)
        else:
            if res["total_count"] or res["items"]:
                raise SystemExit(f"incomplete search results for {q!r}, retry later")
        for it in res["items"]:
            repo = it["repository_url"].removeprefix("https://api.github.com/repos/")
            if repo.split("/")[0].lower() != USER:
                found.append((repo, it))
        if len(res["items"]) < 100:
            return found
        page += 1


def pr_entry(repo, it, state):
    date = it["pull_request"]["merged_at"] if state == "merged" else it["created_at"]
    return {"repo": repo, "number": it["number"], "title": it["title"], "url": it["html_url"],
            "state": state, "date": date[:10]}


def upstream_prs():
    # Search results get truncated for broad queries, so page merged PRs one year at a time.
    prs = {}
    start = int(api(f"/users/{USER}")["created_at"][:4])
    for year in range(start, dt.date.today().year + 1):
        for repo, it in search_prs(f"author:{USER} is:pr is:merged merged:{year}-01-01..{year}-12-31"):
            prs[it["html_url"]] = pr_entry(repo, it, "merged")
        time.sleep(1 if TOKEN else 7)
    # Open PRs are shown too, marked as in review; they turn solid once merged.
    for repo, it in search_prs(f"author:{USER} is:pr is:open is:public"):
        prs[it["html_url"]] = pr_entry(repo, it, "open")
    # Closed-unmerged PRs are still work done; they're drawn faded.
    for repo, it in search_prs(f"author:{USER} is:pr is:closed is:unmerged is:public"):
        prs[it["html_url"]] = pr_entry(repo, it, "closed")
    return sorted((p for p in prs.values() if p["url"] not in EXCLUDE), key=lambda p: p["date"])


def build():
    prs = upstream_prs()
    repos = {}
    for name in sorted({p["repo"] for p in prs}):
        info = api(f"/repos/{name}")
        repos[name] = {
            "name": info["full_name"],
            "stars": info["stargazers_count"],
            "description": info.get("description") or "",
            "all_prs": f"https://github.com/{info['full_name']}/pulls?q=is:pr+author:{USER}+is:merged",
        }
    for p in prs:
        p["repo"] = repos[p["repo"]]["name"]
    repos = {r["name"]: r for r in repos.values()}
    return {"user": USER, "generated": dt.date.today().isoformat(), "prs": prs, "repos": repos}


COLORS = {
    "IaC": "#7b42bc",
    "AI tooling": "#d97757",
    "Self-hosting": "#2f81f7",
    "Observability": "#3fb950",
    "Home automation": "#db61a2",
    "Config management": "#8b949e",
    "Dev tooling": "#d29922",
    "Other": "#8b949e",
}
THEMES = {
    "light": {"bg": "#ffffff", "fg": "#1f2328", "muted": "#656d76", "grid": "#d0d7de"},
    "dark": {"bg": "#0d1117", "fg": "#e6edf3", "muted": "#8d96a0", "grid": "#30363d"},
}


W, H = 880, 260
PAD, TOP, AXIS = 24, 40, H - 40
CHAR_W = 6.8  # rough width of a 12px sans-serif glyph, good enough for overlap checks


def layout(data):
    """Pin and label positions, shared by the README SVG and docs/index.html via oss.json."""
    prs = data["prs"]
    years = [int(p["date"][:4]) for p in prs]
    y0, y1 = min(years), max(years) + 1
    t0, t1 = dt.date(y0, 1, 1).toordinal(), dt.date(y1, 1, 1).toordinal()
    xof = lambda d: PAD + (d.toordinal() - t0) / (t1 - t0) * (W - 2 * PAD)
    smax = math.log10(max(r["stars"] for r in data["repos"].values()) + 1)
    yof = lambda s: TOP + 8 + (1 - math.log10(s + 1) / smax) * (AXIS - TOP - 24)

    pins = []
    for i, p in enumerate(prs):
        r = data["repos"][p["repo"]]
        pins.append({"pr": i, "x": round(xof(dt.date.fromisoformat(p["date"])), 1), "y": round(yof(r["stars"]), 1)})

    # Label each current repo's latest pin, biggest projects first, nudging
    # vertically until the label clears the other labels and pins.
    latest = {}
    for pin in pins:
        repo = prs[pin["pr"]]["repo"]
        if not data["repos"][repo]["legacy"] and prs[pin["pr"]]["state"] != "closed":
            latest[repo] = pin
    boxes, labels = [], []
    for repo in sorted(latest, key=lambda n: -data["repos"][n]["stars"]):
        pin, text = latest[repo], repo.split("/")[1]
        w = len(text) * CHAR_W
        others = [q for q in pins if q is not pin]
        placed = None
        for dy in (0, -16, 16, -32, 32, -48, 48, -64, 64):
            for side in (1, -1):
                lx = pin["x"] + 10 if side == 1 else pin["x"] - 10 - w
                ly = pin["y"] + dy
                box = (lx - 2, ly - 9, lx + w + 2, ly + 5)
                if box[0] < PAD or box[2] > W - PAD or box[1] < TOP - 6 or box[3] > AXIS - 4:
                    continue
                if any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in boxes):
                    continue
                if any(box[0] - 7 < q["x"] < box[2] + 7 and box[1] - 7 < q["y"] < box[3] + 7 for q in others):
                    continue
                placed = (lx, ly, box)
                break
            if placed:
                break
        if not placed:
            continue
        lx, ly, box = placed
        boxes.append(box)
        labels.append({"repo": repo, "text": text, "x": round(lx, 1), "y": round(ly + 4, 1),
                       "leader": ly != pin["y"], "px": pin["x"], "py": pin["y"],
                       "lx": round(lx - 3 if lx > pin["x"] else lx + w + 3, 1)})
    ticks = [{"year": y, "x": round(xof(dt.date(y, 1, 1)), 1)} for y in range(y0, y1 + 1)]
    return {"width": W, "height": H, "axis": AXIS, "pad": PAD, "pins": pins, "labels": labels, "ticks": ticks}


def svg(data, theme):
    # Transparent background so the image sits on whichever GitHub theme the viewer uses.
    c, L = THEMES[theme], data["layout"]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">',
        f'<text x="{PAD}" y="24" font-size="12" fill="{c["muted"]}">upstream PRs: ● merged · ○ in review · faded ○ closed · height = project stars (log) · click for the interactive version</text>',
        f'<line x1="{PAD}" y1="{AXIS}" x2="{W-PAD}" y2="{AXIS}" stroke="{c["grid"]}"/>',
    ]
    for t in L["ticks"]:
        out.append(f'<line x1="{t["x"]}" y1="{AXIS}" x2="{t["x"]}" y2="{AXIS+4}" stroke="{c["grid"]}"/>')
        if t["year"] % 2 == 0:
            out.append(f'<text x="{t["x"]}" y="{AXIS+18}" font-size="11" text-anchor="middle" fill="{c["muted"]}">{t["year"]}</text>')
    for pin in L["pins"]:
        r = data["repos"][data["prs"][pin["pr"]]["repo"]]
        col = COLORS.get(r["area"], COLORS["Other"])
        state = data["prs"][pin["pr"]]["state"]
        top = pin["y"] + (5 if state != "merged" else 0)
        out.append(f'<line x1="{pin["x"]}" y1="{top}" x2="{pin["x"]}" y2="{AXIS}" stroke="{col}" stroke-opacity="0.35"/>')
        if state != "merged":
            fade = ' stroke-opacity="0.45"' if state == "closed" else ""
            out.append(f'<circle cx="{pin["x"]}" cy="{pin["y"]}" r="5" fill="none" stroke="{col}" stroke-width="2"{fade}/>')
        else:
            out.append(f'<circle cx="{pin["x"]}" cy="{pin["y"]}" r="6" fill="{col}" fill-opacity="{0.45 if r["legacy"] else 1}"/>')
    for lab in L["labels"]:
        if lab["leader"]:
            out.append(f'<line x1="{lab["px"]}" y1="{lab["py"]}" x2="{lab["lx"]}" y2="{lab["y"]-4}" stroke="{c["muted"]}" stroke-opacity="0.6"/>')
        out.append(f'<text x="{lab["x"]}" y="{lab["y"]}" font-size="12" fill="{c["fg"]}">{escape(lab["text"])}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def write(data):
    for name, repo in data["repos"].items():
        meta = AREAS.get(name, {})
        repo["area"], repo["legacy"] = meta.get("area", "Other"), meta.get("legacy", False)
    data["layout"] = layout(data)
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "oss.json").write_text(json.dumps(data, indent=2) + "\n")
    for theme in THEMES:
        suffix = "" if theme == "light" else "-dark"
        (docs / f"timeline{suffix}.svg").write_text(svg(data, theme))


def main():
    # --render redraws from the existing oss.json (e.g. after editing data/areas.json) without hitting the API.
    if "--render" in sys.argv:
        data = json.loads((ROOT / "docs" / "oss.json").read_text())
    else:
        data = build()
    write(data)
    print(f"{len(data['prs'])} PRs across {len(data['repos'])} repos")


if __name__ == "__main__":
    main()
