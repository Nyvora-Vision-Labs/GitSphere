#!/usr/bin/env python3
"""
Repo-Vector-Base — GitHub Repository Report Generator (v2)
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
    fetch_all_parallel, build_health_section, export_json,
    append_ai_summary_to_report, build_dependency_section
)
from graph import (
    fetch_file_contents, build_graph, export_graph_json
)

GITHUB_API = "https://api.github.com"
DATE_FMT = "%Y-%m-%dT%H:%M:%SZ"

def parse_repo_input(raw: str) -> tuple[str, str]:
    raw = raw.strip().rstrip("/")
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", raw)
    if match: return match.group(1), match.group(2)
    parts = raw.split("/")
    if len(parts) == 2: return parts[0], parts[1]
    raise ValueError(f"Cannot parse '{raw}'. Use owner/repo or a GitHub URL.")

def build_session(token: str | None = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    if token: s.headers["Authorization"] = f"Bearer {token}"
    return s

def build_markdown(data: dict, graph_stats: dict = None) -> str:
    r = data["repo"]
    lines = []
    
    lines.append(f"# 📦 Repository Report: {r['full_name']}\n")
    lines.append(f"> Auto-generated on **{datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}**\n")
    
    if graph_stats:
        lines.append("## 🕸️ Knowledge Graph Overview")
        lines.append(f"**Total Files Connected:** {graph_stats.get('total_files', 0)}")
        lines.append(f"**Import Edges Analyzed:** {graph_stats.get('total_import_edges', 0)}")
        lines.append(f"**Entry Points Detected:** {len(graph_stats.get('entry_points', []))}\n")

    lines.append(build_health_section(data))
    lines.append(build_dependency_section(data))
    
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Generate a comprehensive Markdown report & Semantic Graph.")
    parser.add_argument("repo", help="GitHub repository — owner/repo or full URL")
    parser.add_argument("--token", "-t", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--output", "-o", default="./reports")
    parser.add_argument("--max-files", type=int, default=250)
    args = parser.parse_args()

    try:
        owner, repo = parse_repo_input(args.repo)
    except ValueError as exc:
        print(f"❌ {exc}")
        sys.exit(1)
        
    print(f"\n🔍 Analyzing repository: {owner}/{repo}\n")
    session = build_session(args.token)

    data = fetch_all_parallel(session, owner, repo)
    if data is None:
        print("❌ Repository not found or not accessible.")
        sys.exit(1)

    # Automatically generate the Graph & JSON brain
    print("\n🕸️ Building Highly-Connected Knowledge Graph...")
    tree = data.get("tree", [])
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    file_contents = fetch_file_contents(
        session, owner, repo, tree, 
        max_files=args.max_files,
        deepseek_key=deepseek_key
    )
    repo_graph = build_graph(file_contents, tree)
    
    os.makedirs(args.output, exist_ok=True)
    graph_json_path = export_graph_json(repo_graph, args.output, owner, repo)
    print(f"✅ Graph JSON saved to: {graph_json_path}")

    # Build and save standard markdown
    import json
    with open(graph_json_path, 'r') as f:
        graph_stats = json.load(f).get("stats", {})
        
    md = build_markdown(data, graph_stats)
    filepath = os.path.join(args.output, f"{owner}_{repo}_report.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)
        
    print(f"✅ Report saved to: {filepath}")

if __name__ == "__main__":
    main()