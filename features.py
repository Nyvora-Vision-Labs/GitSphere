#!/usr/bin/env python3
"""
features.py — Enhanced features for Repo-Vector-Base

1. Parallel API fetching (ThreadPoolExecutor)
2. Retry with exponential backoff
3. Commit activity heatmap
4. Code frequency stats
5. Issue/PR velocity analysis
6. Dependency detection
7. JSON export
8. Repo health score + TL;DR summary
9. Gemini AI-powered report summarization
"""

import base64
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

GITHUB_API = "https://api.github.com"
DATE_FMT = "%Y-%m-%dT%H:%M:%SZ"
MAX_ITEMS = 100

# ── Feature 2: Retry with exponential backoff ──────────────
def api_get_retry(session, path, params=None, max_retries=3):
    """GET with retry + exponential backoff for rate limits."""
    url = f"{GITHUB_API}{path}" if path.startswith("/") else path
    for attempt in range(max_retries):
        try:
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
            if r.status_code in (403, 429):
                # Rate limited — check retry-after or backoff
                retry_after = int(r.headers.get("Retry-After", 0))
                wait = max(retry_after, 2 ** (attempt + 1))
                print(f"⏳  Rate limited. Waiting {wait}s (attempt {attempt+1}/{max_retries})…")
                time.sleep(wait)
                continue
            if r.status_code >= 500 and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return None
        except requests.RequestException:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return None
    return None


def api_get_list_retry(session, path, params=None, max_pages=3):
    """Paginated GET with retry."""
    params = dict(params or {})
    params.setdefault("per_page", MAX_ITEMS)
    results = []
    for page in range(1, max_pages + 1):
        params["page"] = page
        data = api_get_retry(session, path, params)
        if not data:
            break
        if isinstance(data, list):
            results.extend(data)
            if len(data) < params["per_page"]:
                break
        else:
            break
    return results


# ── Feature 1: Parallel API fetching ──────────────────────
def fetch_all_parallel(session, owner, repo):
    """Fetch all data categories in parallel using ThreadPoolExecutor."""
    base = f"/repos/{owner}/{repo}"

    # First fetch repo metadata (needed for default_branch)
    print("📡  Fetching repository metadata …")
    repo_data = api_get_retry(session, base)
    if repo_data is None:
        return None

    default_branch = repo_data.get("default_branch", "main")
    data = {"repo": repo_data}

    # Define all parallel tasks: (key, callable)
    def fetch_simple(key, path, wrapper=None):
        result = api_get_retry(session, path)
        if wrapper and result:
            return key, wrapper(result)
        return key, result

    def fetch_list(key, path, params=None, max_pages=2):
        return key, api_get_list_retry(session, path, params, max_pages)

    tasks = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = []

        # Simple GETs
        futures.append(pool.submit(fetch_simple, "languages", f"{base}/languages"))
        futures.append(pool.submit(fetch_simple, "license", f"{base}/license"))
        futures.append(pool.submit(fetch_simple, "community", f"{base}/community/profile"))
        futures.append(pool.submit(fetch_simple, "readme", f"{base}/readme"))
        futures.append(pool.submit(fetch_simple, "views", f"{base}/traffic/views"))
        futures.append(pool.submit(fetch_simple, "clones", f"{base}/traffic/clones"))
        futures.append(pool.submit(fetch_simple, "workflows", f"{base}/actions/workflows",
                                   lambda d: d.get("workflows", [])))
        futures.append(pool.submit(fetch_simple, "topics", f"{base}/topics",
                                   lambda d: d.get("names", [])))
        futures.append(pool.submit(fetch_simple, "tree",
                                   f"{base}/git/trees/{default_branch}",
                                   lambda d: d.get("tree", [])))

        # New: commit activity + code frequency (Features 3 & 4)
        futures.append(pool.submit(fetch_simple, "commit_activity",
                                   f"{base}/stats/commit_activity"))
        futures.append(pool.submit(fetch_simple, "code_frequency",
                                   f"{base}/stats/code_frequency"))
        futures.append(pool.submit(fetch_simple, "participation",
                                   f"{base}/stats/participation"))

        # List GETs
        futures.append(pool.submit(fetch_list, "contributors", f"{base}/contributors"))
        futures.append(pool.submit(fetch_list, "releases", f"{base}/releases",
                                   {"per_page": 10}, 1))
        futures.append(pool.submit(fetch_list, "tags", f"{base}/tags",
                                   {"per_page": 30}, 1))
        futures.append(pool.submit(fetch_list, "branches", f"{base}/branches",
                                   {"per_page": 30}, 1))
        futures.append(pool.submit(fetch_list, "commits", f"{base}/commits",
                                   {"per_page": 15}, 1))
        futures.append(pool.submit(fetch_list, "issues", f"{base}/issues",
                                   {"per_page": 15, "state": "open"}, 1))
        futures.append(pool.submit(fetch_list, "pulls", f"{base}/pulls",
                                   {"per_page": 15, "state": "open"}, 1))
        futures.append(pool.submit(fetch_list, "deployments", f"{base}/deployments",
                                   {"per_page": 10}, 1))

        # New: closed issues & PRs for velocity (Feature 5)
        futures.append(pool.submit(fetch_list, "closed_issues", f"{base}/issues",
                                   {"per_page": 30, "state": "closed", "sort": "updated",
                                    "direction": "desc"}, 1))
        futures.append(pool.submit(fetch_list, "closed_pulls", f"{base}/pulls",
                                   {"per_page": 30, "state": "closed", "sort": "updated",
                                    "direction": "desc"}, 1))

        completed = 0
        total = len(futures)
        for future in as_completed(futures):
            completed += 1
            try:
                key, value = future.result()
                data[key] = value if value is not None else ([] if key in (
                    "contributors", "releases", "tags", "branches", "commits",
                    "issues", "pulls", "deployments", "workflows", "topics",
                    "tree", "closed_issues", "closed_pulls"
                ) else ({} if key == "languages" else None))
                print(f"  ✓ {key} ({completed}/{total})")
            except Exception as e:
                print(f"  ✗ task failed: {e}")

    return data


# ── Feature 3: Commit Activity Heatmap ────────────────────
def build_commit_activity_section(data):
    """Build a weekly commit activity heatmap."""
    activity = data.get("commit_activity")
    if not activity or not isinstance(activity, list):
        return ""

    lines = ["\n## 📈 Commit Activity (last 52 weeks)\n"]

    # Get last 12 weeks for a compact view
    recent = activity[-12:] if len(activity) >= 12 else activity

    lines.append("| Week Starting | Mon | Tue | Wed | Thu | Fri | Sat | Sun | Total |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for week in recent:
        ts = week.get("week", 0)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        week_str = dt.strftime("%b %d")
        days = week.get("days", [0]*7)
        # Reorder: API gives Sun(0)..Sat(6), we want Mon..Sun
        reordered = days[1:] + [days[0]]
        cells = []
        for count in reordered:
            if count == 0:
                cells.append("·")
            elif count <= 3:
                cells.append(f"{'▪' * count}")
            else:
                cells.append(f"**{count}**")
        total = week.get("total", sum(days))
        lines.append(f"| {week_str} | {' | '.join(cells)} | **{total}** |")

    # Summary
    total_commits = sum(w.get("total", 0) for w in activity)
    avg_per_week = total_commits / len(activity) if activity else 0
    lines.append(f"\n**Total commits (52 weeks):** {total_commits:,}")
    lines.append(f"**Average per week:** {avg_per_week:.1f}\n")

    return "\n".join(lines)


# ── Feature 4: Code Frequency Stats ──────────────────────
def build_code_frequency_section(data):
    """Build lines added/removed over time."""
    freq = data.get("code_frequency")
    if not freq or not isinstance(freq, list):
        return ""

    lines = ["\n## 📉 Code Frequency (last 12 weeks)\n"]

    recent = freq[-12:] if len(freq) >= 12 else freq

    lines.append("| Week | Additions | Deletions | Net Change |")
    lines.append("| --- | --- | --- | --- |")

    total_add = 0
    total_del = 0
    for entry in recent:
        if len(entry) >= 3:
            ts, additions, deletions = entry[0], entry[1], entry[2]
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            week_str = dt.strftime("%b %d, %Y")
            net = additions + deletions  # deletions are negative
            sign = "+" if net >= 0 else ""
            lines.append(f"| {week_str} | +{additions:,} | {deletions:,} | {sign}{net:,} |")
            total_add += additions
            total_del += abs(deletions)

    lines.append(f"\n**Total additions:** +{total_add:,}  ")
    lines.append(f"**Total deletions:** -{total_del:,}  ")
    lines.append(f"**Net change:** {'+' if total_add > total_del else ''}{total_add - total_del:,}\n")

    return "\n".join(lines)


# ── Feature 5: Issue/PR Velocity ──────────────────────────
def build_velocity_section(data):
    """Analyze issue/PR close times and ratios."""
    r = data.get("repo", {})
    closed_issues = [i for i in data.get("closed_issues", []) if "pull_request" not in i]
    closed_pulls = data.get("closed_pulls", [])
    open_issues_list = [i for i in data.get("issues", []) if "pull_request" not in i]
    open_pulls = data.get("pulls", [])

    # Calculate average close time for issues
    issue_close_times = _calc_close_times(closed_issues)
    pr_close_times = _calc_close_times(closed_pulls)

    avg_issue_str = "N/A"
    avg_pr_str = "N/A"
    median_issue_str = "N/A"
    median_pr_str = "N/A"

    if issue_close_times:
        avg_issue_str = _fmt_duration(sum(issue_close_times) / len(issue_close_times))
        sorted_times = sorted(issue_close_times)
        median_issue_str = _fmt_duration(sorted_times[len(sorted_times)//2])

    if pr_close_times:
        avg_pr_str = _fmt_duration(sum(pr_close_times) / len(pr_close_times))
        sorted_times = sorted(pr_close_times)
        median_pr_str = _fmt_duration(sorted_times[len(sorted_times)//2])

    lines = ["\n## ⏱️ Issue & PR Velocity\n"]
    lines.append("| Metric | Issues | Pull Requests |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| Open (sampled) | {len(open_issues_list)} | {len(open_pulls)} |")
    lines.append(f"| Recently Closed (sampled) | {len(closed_issues)} | {len(closed_pulls)} |")
    lines.append(f"| Avg Close Time | {avg_issue_str} | {avg_pr_str} |")
    lines.append(f"| Median Close Time | {median_issue_str} | {median_pr_str} |")
    lines.append("")

    # Merged vs Closed without merge (PRs)
    merged = sum(1 for p in closed_pulls if p.get("merged_at"))
    closed_no_merge = len(closed_pulls) - merged
    if closed_pulls:
        lines.append(f"**PR Merge Rate:** {merged}/{len(closed_pulls)} "
                     f"({merged/len(closed_pulls)*100:.0f}% merged, "
                     f"{closed_no_merge} closed without merge)\n")

    return "\n".join(lines)


def _calc_close_times(items):
    """Calculate close durations in hours for a list of issues/PRs."""
    durations = []
    for item in items:
        created = item.get("created_at")
        closed = item.get("closed_at")
        if created and closed:
            try:
                c = datetime.strptime(created, DATE_FMT)
                cl = datetime.strptime(closed, DATE_FMT)
                hours = (cl - c).total_seconds() / 3600
                if hours >= 0:
                    durations.append(hours)
            except ValueError:
                pass
    return durations


def _fmt_duration(hours):
    """Format hours into human-readable duration."""
    if hours < 1:
        return f"{int(hours * 60)}m"
    if hours < 24:
        return f"{hours:.1f}h"
    days = hours / 24
    if days < 30:
        return f"{days:.1f}d"
    months = days / 30
    return f"{months:.1f}mo"


# ── Feature 6: Dependency Detection ──────────────────────
DEPENDENCY_FILES = {
    "package.json": "Node.js (npm)",
    "yarn.lock": "Node.js (yarn)",
    "pnpm-lock.yaml": "Node.js (pnpm)",
    "requirements.txt": "Python (pip)",
    "Pipfile": "Python (pipenv)",
    "pyproject.toml": "Python (pyproject)",
    "setup.py": "Python (setuptools)",
    "Cargo.toml": "Rust (cargo)",
    "go.mod": "Go (modules)",
    "Gemfile": "Ruby (bundler)",
    "composer.json": "PHP (composer)",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java/Kotlin (Gradle)",
    "build.gradle.kts": "Java/Kotlin (Gradle KTS)",
    "pubspec.yaml": "Dart/Flutter (pub)",
    "Package.swift": "Swift (SPM)",
    "mix.exs": "Elixir (mix)",
    "Makefile": "Make",
    "CMakeLists.txt": "C/C++ (CMake)",
    "vcpkg.json": "C/C++ (vcpkg)",
    "deno.json": "Deno",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
    ".terraform.lock.hcl": "Terraform",
}


def build_dependency_section(data):
    """Detect dependency/build files from the tree and optionally parse them."""
    tree = data.get("tree", [])
    if not tree:
        return ""

    file_paths = {item["path"] for item in tree if item.get("type") == "blob"}

    found = {}
    for dep_file, ecosystem in DEPENDENCY_FILES.items():
        matches = [p for p in file_paths if p.endswith(f"/{dep_file}") or p == dep_file]
        if matches:
            found[ecosystem] = found.get(ecosystem, []) + matches

    if not found:
        return ""

    lines = ["\n## 📦 Detected Dependencies & Build Systems\n"]
    lines.append("| Ecosystem | File | Path |")
    lines.append("| --- | --- | --- |")

    for ecosystem in sorted(found.keys()):
        for path in sorted(found[ecosystem]):
            filename = path.split("/")[-1]
            lines.append(f"| {ecosystem} | `{filename}` | `{path}` |")

    lines.append(f"\n**Ecosystems detected:** {len(found)}\n")

    return "\n".join(lines)


# ── Feature 7: JSON Export ────────────────────────────────
def export_json(data, output_dir, owner, repo):
    """Save raw API data as JSON alongside the markdown report."""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{owner}_{repo}_data.json")

    # Make data JSON-serializable (strip non-serializable bits)
    clean = {}
    for key, value in data.items():
        try:
            json.dumps(value)
            clean[key] = value
        except (TypeError, ValueError):
            clean[key] = str(value)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False, default=str)

    return filepath


# ── Feature 8: Health Score + TL;DR ──────────────────────
def calculate_health_score(data):
    """Calculate a 0-100 health score across multiple dimensions."""
    r = data.get("repo", {})
    scores = {}

    # 1. Documentation (20 pts)
    doc_score = 0
    community = data.get("community") or {}
    files = community.get("files", {})
    if files.get("readme"):
        doc_score += 6
    if files.get("contributing"):
        doc_score += 4
    if files.get("code_of_conduct"):
        doc_score += 3
    if files.get("license") or r.get("license"):
        doc_score += 4
    if files.get("issue_template"):
        doc_score += 1.5
    if files.get("pull_request_template"):
        doc_score += 1.5
    scores["Documentation"] = min(doc_score, 20)

    # 2. Activity (20 pts)
    activity_score = 0
    commits = data.get("commits", [])
    if commits:
        last_commit_date = commits[0].get("commit", {}).get("author", {}).get("date")
        if last_commit_date:
            try:
                dt = datetime.strptime(last_commit_date, DATE_FMT)
                days_since = (datetime.utcnow() - dt).days
                if days_since <= 7:
                    activity_score += 10
                elif days_since <= 30:
                    activity_score += 8
                elif days_since <= 90:
                    activity_score += 5
                elif days_since <= 365:
                    activity_score += 2
            except ValueError:
                pass

    commit_activity = data.get("commit_activity")
    if commit_activity and isinstance(commit_activity, list):
        recent_4 = commit_activity[-4:] if len(commit_activity) >= 4 else commit_activity
        recent_commits = sum(w.get("total", 0) for w in recent_4)
        if recent_commits >= 20:
            activity_score += 10
        elif recent_commits >= 10:
            activity_score += 7
        elif recent_commits >= 3:
            activity_score += 4
        elif recent_commits >= 1:
            activity_score += 2
    scores["Activity"] = min(activity_score, 20)

    # 3. Community (20 pts)
    community_score = 0
    stars = r.get("stargazers_count", 0)
    if stars >= 1000:
        community_score += 7
    elif stars >= 100:
        community_score += 5
    elif stars >= 10:
        community_score += 3
    elif stars >= 1:
        community_score += 1

    contribs = data.get("contributors", [])
    if len(contribs) >= 20:
        community_score += 7
    elif len(contribs) >= 5:
        community_score += 5
    elif len(contribs) >= 2:
        community_score += 3
    elif len(contribs) >= 1:
        community_score += 1

    forks = r.get("forks_count", 0)
    if forks >= 100:
        community_score += 6
    elif forks >= 10:
        community_score += 4
    elif forks >= 1:
        community_score += 2
    scores["Community"] = min(community_score, 20)

    # 4. CI/CD (15 pts)
    ci_score = 0
    workflows = data.get("workflows", [])
    if workflows:
        ci_score += 8
        active = sum(1 for w in workflows if w.get("state") == "active")
        if active >= 3:
            ci_score += 7
        elif active >= 1:
            ci_score += 4
    scores["CI/CD"] = min(ci_score, 15)

    # 5. Maintenance (15 pts)
    maint_score = 0
    releases = data.get("releases", [])
    if releases:
        maint_score += 5
        latest = releases[0].get("published_at")
        if latest:
            try:
                dt = datetime.strptime(latest, DATE_FMT)
                days = (datetime.utcnow() - dt).days
                if days <= 90:
                    maint_score += 5
                elif days <= 365:
                    maint_score += 3
            except ValueError:
                pass
    if not r.get("archived"):
        maint_score += 3
    if r.get("has_issues"):
        maint_score += 2
    scores["Maintenance"] = min(maint_score, 15)

    # 6. Code Quality signals (10 pts)
    cq_score = 0
    langs = data.get("languages", {})
    if langs:
        cq_score += 3
    tree = data.get("tree", [])
    tree_paths = [t.get("path", "") for t in tree] if tree else []
    test_indicators = ["test", "tests", "spec", "specs", "__tests__"]
    if any(p.split("/")[0].lower() in test_indicators for p in tree_paths):
        cq_score += 4
    ci_indicators = [".github/workflows", ".circleci", ".travis.yml", "Jenkinsfile"]
    if any(any(p.startswith(ci) for p in tree_paths) for ci in ci_indicators):
        cq_score += 3
    scores["Code Quality"] = min(cq_score, 10)

    total = sum(scores.values())
    return total, scores


def build_health_section(data):
    """Build the health score + TL;DR summary section."""
    total, scores = calculate_health_score(data)
    r = data.get("repo", {})

    # Grade
    if total >= 90:
        grade, color = "A+", "🟢"
    elif total >= 80:
        grade, color = "A", "🟢"
    elif total >= 70:
        grade, color = "B", "🟡"
    elif total >= 60:
        grade, color = "C", "🟠"
    elif total >= 50:
        grade, color = "D", "🟠"
    else:
        grade, color = "F", "🔴"

    lines = ["\n## 🏆 Repository Health Score\n"]
    lines.append(f"### {color} Overall: **{total}/100** (Grade: **{grade}**)\n")

    # Score breakdown
    lines.append("| Category | Score | Max | Bar |")
    lines.append("| --- | --- | --- | --- |")
    max_scores = {
        "Documentation": 20, "Activity": 20, "Community": 20,
        "CI/CD": 15, "Maintenance": 15, "Code Quality": 10,
    }
    for cat in ["Documentation", "Activity", "Community", "CI/CD", "Maintenance", "Code Quality"]:
        s = scores.get(cat, 0)
        mx = max_scores[cat]
        pct = s / mx * 100 if mx else 0
        filled = int(pct / 5)
        bar = "█" * filled + "░" * (20 - filled)
        lines.append(f"| {cat} | {s:.0f} | {mx} | {bar} |")
    lines.append("")

    # TL;DR Summary
    lines.append("### 📝 TL;DR\n")
    name = r.get("full_name", "This repository")
    desc = r.get("description") or "No description"
    stars = r.get("stargazers_count", 0)
    forks = r.get("forks_count", 0)
    langs = data.get("languages", {})
    top_lang = max(langs, key=langs.get) if langs else "unknown"

    contribs = data.get("contributors", [])
    age_str = ""
    created = r.get("created_at")
    if created:
        try:
            dt = datetime.strptime(created, DATE_FMT)
            days = (datetime.utcnow() - dt).days
            if days < 30:
                age_str = f"{days} days"
            elif days < 365:
                age_str = f"{days//30} months"
            else:
                years = days // 365
                age_str = f"{years} year{'s' if years > 1 else ''}"
        except ValueError:
            pass

    summary_parts = [
        f"**{name}** is a {top_lang}-based project",
        f'described as _"{desc}"_.',
        f"With **{stars:,} stars** and **{forks:,} forks**,",
        f"it has **{len(contribs)} contributors**",
    ]
    if age_str:
        summary_parts.append(f"and has been active for **{age_str}**.")
    else:
        summary_parts.append(".")

    # Activity assessment
    commits_data = data.get("commit_activity")
    if commits_data and isinstance(commits_data, list) and len(commits_data) >= 4:
        recent = sum(w.get("total", 0) for w in commits_data[-4:])
        if recent >= 20:
            summary_parts.append(f"The project is **very active** with {recent} commits in the last month.")
        elif recent >= 5:
            summary_parts.append(f"The project has **moderate activity** with {recent} commits in the last month.")
        elif recent >= 1:
            summary_parts.append(f"The project has **low activity** with {recent} commits in the last month.")
        else:
            summary_parts.append("The project appears to be **inactive** recently.")

    lines.append(" ".join(summary_parts) + "\n")

    return "\n".join(lines)


# ── Feature 9: Gemini AI Summarization ───────────────────
def summarize_with_gemini(report_md: str, api_key: str | None = None) -> str | None:
    """
    Use Gemini to generate an AI-powered executive summary of the report.

    Args:
        report_md: The full markdown report content.
        api_key: Gemini API key. If None, reads from GEMINI_API_KEY env var / .env file.

    Returns:
        The AI-generated summary as markdown, or None on failure.
    """
    # Load .env if needed
    from dotenv import load_dotenv
    load_dotenv()

    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("⚠️  No Gemini API key found. Set GEMINI_API_KEY in .env or pass --gemini-key.")
        return None

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        # Truncate report if too long (Gemini has context limits)
        max_chars = 60000
        content = report_md[:max_chars] if len(report_md) > max_chars else report_md

        prompt = f"""You are an expert software analyst. Analyze the following GitHub repository report and generate a comprehensive executive summary in Markdown format.

Your summary should include:

1. **Project Overview** — What the project is, its purpose, and primary technology stack.
2. **Health Assessment** — Overall health of the project based on the health score, activity, and community metrics.
3. **Key Strengths** — What the project does well (active community, good docs, CI/CD, etc.).
4. **Areas for Improvement** — What could be better (missing docs, low activity, no tests, etc.).
5. **Activity Analysis** — Recent commit patterns, contributor engagement, and release cadence.
6. **Notable Metrics** — Key stats worth highlighting (stars, forks, contributors, languages).
7. **Recommendation** — A brief verdict: is this project well-maintained? Safe to depend on?

Keep it concise but insightful. Use bullet points and markdown formatting. Do NOT include any code blocks.

---

REPORT:
{content}"""

        models_to_try = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]

        for model_name in models_to_try:
            for attempt in range(2):
                try:
                    print(f"    Trying {model_name} (attempt {attempt + 1})…")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                    )
                    return response.text
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        if attempt == 0:
                            # Extract retry delay if available
                            import re as _re
                            delay_match = _re.search(r"retry in ([\d.]+)s", err_str)
                            wait = float(delay_match.group(1)) + 1 if delay_match else 20
                            print(f"    ⏳ Rate limited. Waiting {wait:.0f}s…")
                            time.sleep(wait)
                            continue
                        else:
                            print(f"    ⚠️  {model_name} rate limited, trying next model…")
                            break
                    else:
                        print(f"⚠️  Gemini summarization failed ({model_name}): {e}")
                        return None

        print("⚠️  All Gemini models exhausted.")
        return None

    except ImportError:
        print("⚠️  google-genai not installed. Run: pip install google-genai")
        return None
    except Exception as e:
        print(f"⚠️  Gemini setup failed: {e}")
        return None


def append_ai_summary_to_report(report_path: str, api_key: str | None = None) -> bool:
    """
    Read a report file, generate an AI summary, and prepend it to the report.

    Returns True if successful, False otherwise.
    """
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report_md = f.read()
    except FileNotFoundError:
        print(f"⚠️  Report file not found: {report_path}")
        return False

    print("🤖  Generating AI summary with Gemini …")
    summary = summarize_with_gemini(report_md, api_key)

    if not summary:
        return False

    # Insert AI summary after the title/timestamp block
    ai_section = f"""
## 🤖 AI-Powered Executive Summary

> _Generated by Google Gemini_

{summary}

---
"""

    # Find the end of the header (after the blockquote timestamp line)
    lines = report_md.split("\n")
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("> Auto-generated on"):
            insert_idx = i + 1
            break

    # Insert the AI summary
    lines.insert(insert_idx, ai_section)
    updated = "\n".join(lines)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(updated)

    print("✅  AI summary added to report!")
    return True
