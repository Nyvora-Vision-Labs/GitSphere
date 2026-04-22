#!/usr/bin/env python3
"""
Repo-Vector-Base — GitHub Repository Report Generator (v2)

Takes a GitHub repository (owner/repo or full URL) as input and generates
a comprehensive Markdown report with:
  - Parallel API fetching (~5x faster)
  - Retry with exponential backoff
  - Commit activity heatmap
  - Code frequency stats
  - Issue/PR velocity analysis
  - Dependency detection
  - JSON data export
  - Health score + TL;DR summary

Usage:
    python repo_report.py <owner/repo or GitHub URL> [--token YOUR_TOKEN] [--output DIR]

Examples:
    python repo_report.py facebook/react
    python repo_report.py https://github.com/torvalds/linux --token ghp_xxx
    python repo_report.py pallets/flask --output ./reports --json
"""

import argparse
import base64
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

from dotenv import load_dotenv
load_dotenv()

from features import (
    fetch_all_parallel,
    build_commit_activity_section,
    build_code_frequency_section,
    build_velocity_section,
    build_dependency_section,
    build_health_section,
    export_json,
    append_ai_summary_to_report,
)

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
GITHUB_API = "https://api.github.com"
DATE_FMT = "%Y-%m-%dT%H:%M:%SZ"


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def parse_repo_input(raw: str) -> tuple[str, str]:
    """Extract (owner, repo) from 'owner/repo' or a GitHub URL."""
    raw = raw.strip().rstrip("/")
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", raw)
    if match:
        return match.group(1), match.group(2)
    parts = raw.split("/")
    if len(parts) == 2:
        return parts[0], parts[1]
    print(f"❌  Cannot parse '{raw}'. Use owner/repo or a GitHub URL.")
    sys.exit(1)


def build_session(token: str | None = None) -> requests.Session:
    """Return a requests.Session with auth + accept headers."""
    s = requests.Session()
    s.headers.update({
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


def fmt_date(iso: str | None) -> str:
    """Human-friendly date string."""
    if not iso:
        return "N/A"
    try:
        dt = datetime.strptime(iso, DATE_FMT).replace(tzinfo=timezone.utc)
        return dt.strftime("%B %d, %Y at %H:%M UTC")
    except ValueError:
        return iso


def fmt_number(n: int | None) -> str:
    """Format large numbers with commas."""
    if n is None:
        return "N/A"
    return f"{n:,}"


def time_ago(iso: str | None) -> str:
    """Return a relative-time string like '3 days ago'."""
    if not iso:
        return ""
    try:
        dt = datetime.strptime(iso, DATE_FMT).replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        days = delta.days
        if days == 0:
            hours = delta.seconds // 3600
            return f"{hours}h ago" if hours else "just now"
        if days < 30:
            return f"{days}d ago"
        if days < 365:
            return f"{days // 30}mo ago"
        return f"{days // 365}y ago"
    except ValueError:
        return ""


# ──────────────────────────────────────────────
# Markdown builder
# ──────────────────────────────────────────────
def build_markdown(data: dict) -> str:
    """Build the full Markdown report string."""
    r = data["repo"]
    lines: list[str] = []

    def heading(level: int, text: str):
        lines.append(f"\n{'#' * level} {text}\n")

    def table(headers: list[str], rows: list[list[str]]):
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
        lines.append("")

    # ── Title ──
    heading(1, f"📦 Repository Report: {r['full_name']}")
    lines.append(f"> Auto-generated on **{datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}**\n")

    # ── NEW: Health Score + TL;DR (Feature 8) ──
    lines.append(build_health_section(data))

    # ── Overview ──
    heading(2, "📋 Overview")
    desc = r.get("description") or "_No description provided._"
    lines.append(f"**Description:** {desc}\n")
    if r.get("homepage"):
        lines.append(f"**Homepage:** {r['homepage']}\n")
    lines.append(f"**URL:** {r['html_url']}\n")
    lines.append(f"**Default Branch:** `{r['default_branch']}`\n")
    lines.append(f"**Visibility:** {r.get('visibility', 'public').capitalize()}\n")
    lines.append(f"**Archived:** {'Yes ⚠️' if r.get('archived') else 'No'}\n")
    lines.append(f"**Fork:** {'Yes' if r.get('fork') else 'No'}\n")
    if r.get("fork") and r.get("parent"):
        lines.append(f"**Forked From:** [{r['parent']['full_name']}]({r['parent']['html_url']})\n")
    lines.append(f"**Created:** {fmt_date(r.get('created_at'))}\n")
    lines.append(f"**Last Push:** {fmt_date(r.get('pushed_at'))}\n")
    lines.append(f"**Last Updated:** {fmt_date(r.get('updated_at'))}\n")

    # ── Statistics ──
    heading(2, "⭐ Statistics")
    table(
        ["Metric", "Count"],
        [
            ["⭐ Stars", fmt_number(r.get("stargazers_count"))],
            ["👀 Watchers", fmt_number(r.get("subscribers_count"))],
            ["🍴 Forks", fmt_number(r.get("forks_count"))],
            ["🐛 Open Issues", fmt_number(r.get("open_issues_count"))],
            ["📦 Size", f"{fmt_number(r.get('size'))} KB"],
            ["🔀 Network Count", fmt_number(r.get("network_count"))],
        ],
    )

    # ── Topics ──
    if data.get("topics"):
        heading(2, "🏷️ Topics")
        lines.append(" ".join(f"`{t}`" for t in data["topics"]) + "\n")

    # ── Languages ──
    if data.get("languages"):
        heading(2, "💻 Languages")
        langs = data["languages"]
        total = sum(langs.values()) or 1
        rows = []
        for lang, bytes_ in sorted(langs.items(), key=lambda x: -x[1]):
            pct = bytes_ / total * 100
            bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
            rows.append([lang, f"{fmt_number(bytes_)} bytes", f"{pct:.1f}%", bar])
        table(["Language", "Bytes", "Percentage", ""], rows)

    # ── License ──
    heading(2, "📜 License")
    lic = data.get("license")
    if lic and lic.get("license"):
        li = lic["license"]
        lines.append(f"**Name:** {li.get('name', 'N/A')}\n")
        lines.append(f"**SPDX ID:** `{li.get('spdx_id', 'N/A')}`\n")
    elif r.get("license"):
        lines.append(f"**Name:** {r['license'].get('name', 'N/A')}\n")
        lines.append(f"**SPDX ID:** `{r['license'].get('spdx_id', 'N/A')}`\n")
    else:
        lines.append("_No license detected._\n")

    # ── Owner ──
    heading(2, "👤 Owner")
    owner = r.get("owner", {})
    lines.append(f"**Username:** [{owner.get('login', 'N/A')}]({owner.get('html_url', '')})\n")
    lines.append(f"**Type:** {owner.get('type', 'N/A')}\n")
    lines.append(f"**Avatar:** ![avatar]({owner.get('avatar_url', '')})\n")

    # ── Contributors ──
    contribs = data.get("contributors", [])
    if contribs:
        heading(2, "👥 Top Contributors")
        rows = []
        for i, c in enumerate(contribs[:20], 1):
            rows.append([
                str(i),
                f"[{c.get('login', '?')}]({c.get('html_url', '')})",
                fmt_number(c.get("contributions")),
            ])
        table(["#", "Contributor", "Contributions"], rows)

    # ── NEW: Commit Activity Heatmap (Feature 3) ──
    lines.append(build_commit_activity_section(data))

    # ── NEW: Code Frequency (Feature 4) ──
    lines.append(build_code_frequency_section(data))

    # ── NEW: Issue/PR Velocity (Feature 5) ──
    lines.append(build_velocity_section(data))

    # ── Branches ──
    branches = data.get("branches", [])
    if branches:
        heading(2, "🌿 Branches")
        lines.append(f"**Total shown:** {len(branches)}\n")
        for b in branches:
            protected = " 🔒" if b.get("protected") else ""
            lines.append(f"- `{b['name']}`{protected}")
        lines.append("")

    # ── Tags ──
    tags = data.get("tags", [])
    if tags:
        heading(2, "🏷️ Tags")
        lines.append(f"**Total shown:** {len(tags)}\n")
        for t in tags[:20]:
            lines.append(f"- `{t['name']}`")
        lines.append("")

    # ── Releases ──
    releases = data.get("releases", [])
    if releases:
        heading(2, "🚀 Releases")
        for rel in releases[:10]:
            tag = rel.get("tag_name", "?")
            name = rel.get("name") or tag
            pre = " ⚠️ Pre-release" if rel.get("prerelease") else ""
            draft = " 📝 Draft" if rel.get("draft") else ""
            lines.append(f"### {name} (`{tag}`){pre}{draft}\n")
            lines.append(f"- **Published:** {fmt_date(rel.get('published_at'))}")
            lines.append(f"- **Author:** {rel.get('author', {}).get('login', 'N/A')}")
            assets = rel.get("assets", [])
            if assets:
                lines.append(f"- **Assets:** {len(assets)}")
                for a in assets[:5]:
                    lines.append(f"  - [{a['name']}]({a['browser_download_url']}) "
                                 f"({fmt_number(a.get('download_count', 0))} downloads)")
            body = (rel.get("body") or "").strip()
            if body:
                if len(body) > 500:
                    body = body[:500] + " …"
                lines.append(f"\n<details><summary>Release Notes</summary>\n\n{body}\n\n</details>\n")
            lines.append("")

    # ── Recent Commits ──
    commits = data.get("commits", [])
    if commits:
        heading(2, "📝 Recent Commits")
        rows = []
        for c in commits[:15]:
            sha = c["sha"][:7]
            msg = (c["commit"]["message"].split("\n")[0])[:80]
            author = c["commit"]["author"]["name"]
            date = time_ago(c["commit"]["author"].get("date"))
            rows.append([f"`{sha}`", msg, author, date])
        table(["SHA", "Message", "Author", "When"], rows)

    # ── Open Issues ──
    issues = [i for i in data.get("issues", []) if "pull_request" not in i]
    if issues:
        heading(2, "🐛 Open Issues (recent)")
        rows = []
        for i in issues[:15]:
            labels = ", ".join(f"`{l['name']}`" for l in i.get("labels", []))
            rows.append([
                f"[#{i['number']}]({i['html_url']})",
                (i.get("title") or "")[:70],
                i.get("user", {}).get("login", "?"),
                labels or "—",
                time_ago(i.get("created_at")),
            ])
        table(["#", "Title", "Author", "Labels", "Opened"], rows)

    # ── Open Pull Requests ──
    pulls = data.get("pulls", [])
    if pulls:
        heading(2, "🔀 Open Pull Requests (recent)")
        rows = []
        for pr in pulls[:15]:
            labels = ", ".join(f"`{l['name']}`" for l in pr.get("labels", []))
            rows.append([
                f"[#{pr['number']}]({pr['html_url']})",
                (pr.get("title") or "")[:70],
                pr.get("user", {}).get("login", "?"),
                labels or "—",
                time_ago(pr.get("created_at")),
            ])
        table(["#", "Title", "Author", "Labels", "Opened"], rows)

    # ── CI / CD Workflows ──
    workflows = data.get("workflows", [])
    if workflows:
        heading(2, "⚙️ GitHub Actions Workflows")
        rows = []
        for wf in workflows:
            rows.append([
                wf.get("name", "?"),
                f"`{wf.get('state', '?')}`",
                wf.get("path", ""),
            ])
        table(["Workflow", "State", "Path"], rows)

    # ── Community Profile ──
    community = data.get("community")
    if community:
        heading(2, "🤝 Community Profile")
        health = community.get("health_percentage", "?")
        lines.append(f"**Health Percentage:** {health}%\n")
        files = community.get("files", {})
        checks = {
            "Code of Conduct": files.get("code_of_conduct"),
            "Contributing Guide": files.get("contributing"),
            "Issue Template": files.get("issue_template"),
            "Pull Request Template": files.get("pull_request_template"),
            "README": files.get("readme"),
            "License": files.get("license"),
        }
        for label, val in checks.items():
            status = "✅" if val else "❌"
            lines.append(f"- {status} {label}")
        lines.append("")

    # ── NEW: Dependency Detection (Feature 6) ──
    lines.append(build_dependency_section(data))

    # ── Deployments ──
    deployments = data.get("deployments", [])
    if deployments:
        heading(2, "🌐 Deployments (recent)")
        rows = []
        for d in deployments[:10]:
            rows.append([
                d.get("environment", "?"),
                f"`{d.get('ref', '?')}`",
                d.get("creator", {}).get("login", "?"),
                fmt_date(d.get("created_at")),
            ])
        table(["Environment", "Ref", "Creator", "Created"], rows)

    # ── Traffic ──
    views = data.get("views")
    clones = data.get("clones")
    if views or clones:
        heading(2, "📊 Traffic (last 14 days)")
        if views:
            lines.append(f"- **Views:** {fmt_number(views.get('count'))} "
                         f"(unique: {fmt_number(views.get('uniques'))})")
        if clones:
            lines.append(f"- **Clones:** {fmt_number(clones.get('count'))} "
                         f"(unique: {fmt_number(clones.get('uniques'))})")
        lines.append("")

    # ── Directory Tree ──
    tree = data.get("tree", [])
    if tree:
        heading(2, "📂 Directory Structure")
        tree_lines = []
        shown = 0
        for item in tree:
            if shown >= 200:
                tree_lines.append(f"… and {len(tree) - 200} more entries")
                break
            path = item.get("path", "")
            type_ = item.get("type", "")
            if type_ == "tree":
                tree_lines.append(f"📁 {path}/")
            else:
                size = item.get("size", 0)
                tree_lines.append(f"   📄 {path} ({fmt_number(size)} B)")
            shown += 1
        lines.append("```")
        lines.extend(tree_lines)
        lines.append("```\n")
        lines.append(f"**Total entries:** {len(tree)}\n")

    # ── README Preview ──
    readme = data.get("readme")
    if readme:
        heading(2, "📖 README Preview")
        try:
            content = base64.b64decode(readme["content"]).decode("utf-8", errors="replace")
            if len(content) > 3000:
                content = content[:3000] + "\n\n_… (truncated)_"
            lines.append("<details><summary>Click to expand README</summary>\n")
            lines.append(content)
            lines.append("\n</details>\n")
        except Exception:
            lines.append("_Could not decode README._\n")

    # ── Footer ──
    lines.append("---")
    lines.append(f"_Report generated by [Repo-Vector-Base](https://github.com/Nyvora-Vision-Labs/Repo-Vector-Base) "
                 f"v2.0 • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_\n")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Generate a comprehensive Markdown report for any GitHub repository.",
        epilog="Examples:\n"
               "  python repo_report.py facebook/react\n"
               "  python repo_report.py https://github.com/torvalds/linux --token ghp_xxx\n"
               "  python repo_report.py pallets/flask --output ./reports --json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("repo",
                        help="GitHub repository — owner/repo or full URL")
    parser.add_argument("--token", "-t", default=os.environ.get("GITHUB_TOKEN"),
                        help="GitHub personal access token (or set GITHUB_TOKEN env var)")
    parser.add_argument("--output", "-o", default="./reports",
                        help="Directory to save the report (default: ./reports)")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Also export raw API data as JSON")
    parser.add_argument("--gemini-key", default=os.environ.get("GEMINI_API_KEY"),
                        help="Gemini API key for AI summary (or set GEMINI_API_KEY in .env)")
    parser.add_argument("--no-ai", action="store_true",
                        help="Skip AI-powered summary generation")
    args = parser.parse_args()

    owner, repo = parse_repo_input(args.repo)
    print(f"\n🔍  Analyzing repository: {owner}/{repo}\n")

    session = build_session(args.token)

    # Feature 1: Parallel fetching
    start = time.time()
    data = fetch_all_parallel(session, owner, repo)
    elapsed = time.time() - start

    if data is None:
        print("❌  Repository not found or not accessible.")
        sys.exit(1)

    print(f"\n⚡ Data fetched in {elapsed:.1f}s (parallel)\n")

    md = build_markdown(data)

    # Write markdown
    os.makedirs(args.output, exist_ok=True)
    filename = f"{owner}_{repo}_report.md"
    filepath = os.path.join(args.output, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"✅  Report saved to: {filepath}")
    print(f"    ({len(md):,} characters, {md.count(chr(10)):,} lines)")

    # Feature 7: JSON export
    if args.json:
        json_path = export_json(data, args.output, owner, repo)
        print(f"✅  JSON data saved to: {json_path}")

    # Print health score summary
    from features import calculate_health_score
    total, _ = calculate_health_score(data)
    grade = "A+" if total >= 90 else "A" if total >= 80 else "B" if total >= 70 else "C" if total >= 60 else "D" if total >= 50 else "F"
    print(f"\n🏆  Health Score: {total}/100 (Grade: {grade})")

    # Feature 9: Gemini AI summary
    if not args.no_ai:
        append_ai_summary_to_report(filepath, api_key=args.gemini_key)


if __name__ == "__main__":
    main()
