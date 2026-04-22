# 📦 Repo-Vector-Base

A powerful CLI tool that generates **comprehensive Markdown reports** for any public GitHub repository. Just give it a repo name — it pulls everything from the GitHub API and saves a beautifully formatted `.md` file.

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run it
python repo_report.py facebook/react
```

Your report will be saved to `./reports/facebook_react_report.md`.

---

## 📖 Usage

```
python repo_report.py <owner/repo or GitHub URL> [--token TOKEN] [--output DIR] [--json]
```

| Argument     | Description                                      | Default           |
|------------- |------------------------------------------------- |------------------ |
| `repo`       | `owner/repo` or full GitHub URL                  | _(required)_      |
| `--token`    | GitHub PAT for higher rate limits / private repos | `$GITHUB_TOKEN`   |
| `--output`   | Directory to save the report                     | `./reports`       |
| `--json`     | Also export raw API data as JSON                 | `false`           |

### Examples

```bash
# Simple
python repo_report.py torvalds/linux

# Full URL
python repo_report.py https://github.com/pallets/flask

# With auth token (5000 req/hr instead of 60)
python repo_report.py myorg/private-repo --token ghp_xxxxxxxxxxxx

# With JSON export
python repo_report.py vercel/next.js --output ~/Desktop/reports --json
```

---

## ✨ Features (v2)

### Core Report Sections
| Section                     | Details                                              |
|---------------------------- |----------------------------------------------------- |
| 🏆 Health Score + TL;DR     | Auto-calculated 0–100 score across 6 dimensions      |
| 📋 Overview                | Description, URL, visibility, creation date, etc.    |
| ⭐ Statistics               | Stars, forks, watchers, open issues, repo size       |
| 🏷️ Topics                  | All repository topics                                |
| 💻 Languages               | Byte-count breakdown with percentage bars            |
| 📜 License                 | License name and SPDX identifier                     |
| 👤 Owner                   | Username, type, avatar                               |
| 👥 Top Contributors        | Top 20 contributors with commit counts               |
| 📈 Commit Activity         | Weekly commit heatmap (last 12 weeks)                |
| 📉 Code Frequency          | Lines added/removed over time                        |
| ⏱️ Issue/PR Velocity       | Avg/median close times, merge rates                  |
| 🌿 Branches                | All branches with protection status                  |
| 🏷️ Tags                    | Recent tags                                          |
| 🚀 Releases                | Last 10 releases with assets & release notes         |
| 📝 Recent Commits          | Last 15 commits with SHA, message, author            |
| 🐛 Open Issues             | Recent open issues with labels                       |
| 🔀 Open Pull Requests      | Recent open PRs with labels                          |
| ⚙️ GitHub Actions          | CI/CD workflow names, states, paths                  |
| 🤝 Community Profile       | Health score, CODE_OF_CONDUCT, CONTRIBUTING, etc.    |
| 📦 Dependencies            | Auto-detected build systems & dependency files       |
| 🌐 Deployments             | Recent deployment environments                       |
| 📊 Traffic                 | Views & clones (requires push access + token)        |
| 📂 Directory Structure     | Full file tree of the repository                     |
| 📖 README Preview          | First 3000 characters of the README                  |

### Engine Features
| Feature                      | Details                                              |
|----------------------------- |----------------------------------------------------- |
| ⚡ Parallel Fetching         | 10-thread concurrent API calls (~5x faster)          |
| 🔄 Retry + Backoff          | Automatic retry with exponential backoff for rate limits |
| 💾 JSON Export               | `--json` flag exports raw API data alongside report  |
| 🏆 Health Score              | Scored across Documentation, Activity, Community, CI/CD, Maintenance, Code Quality |

---

## 🔑 Authentication

Without a token you get **60 requests/hour** (may not be enough for large repos). With a token you get **5,000 requests/hour** and access to private repos.

```bash
# Option 1: pass directly
python repo_report.py owner/repo --token ghp_xxxx

# Option 2: environment variable
export GITHUB_TOKEN=ghp_xxxx
python repo_report.py owner/repo

# Option 3: use gh CLI token
python repo_report.py owner/repo --token $(gh auth token)
```

---

## 📁 Project Structure

```
Repo-Vector-Base/
├── repo_report.py       # Main CLI tool & markdown builder
├── features.py          # 8 feature modules (parallel, retry, analysis, etc.)
├── requirements.txt     # Python dependencies
├── readme.md            # This file
├── .gitignore           # Ignores reports/ and Python cache
└── reports/             # Generated reports (git-ignored)
    ├── *_report.md      # Markdown reports
    └── *_data.json      # Raw JSON data (with --json flag)
```

---

## 📄 License

MIT
