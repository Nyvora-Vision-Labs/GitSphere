# 📦 Repo-Vector-Base

> Transform any GitHub repo into a knowledge base — save it as a detailed Markdown report, dependency graph, and LLM-ready context doc.

---

## 🚀 Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/Nyvora-Vision-Labs/Repo-Vector-Base.git
cd Repo-Vector-Base

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up your API keys (optional but recommended)
cp .env.example .env
# Edit .env with your keys:
#   GITHUB_TOKEN=ghp_xxxx        (for higher rate limits)
#   DEEPSEEK_API_KEY=sk-xxxx      (for AI summaries and analysis)

# 4. Generate a report
python repo_report.py facebook/react
```

Your report will be saved to `./reports/facebook_react_report.md` 🎉

---

## 📖 Usage

```bash
python repo_report.py <owner/repo or GitHub URL> [options]
```

### Options

| Flag             | Description                                           | Default         |
|----------------- |------------------------------------------------------ |---------------- |
| `--token`, `-t`  | GitHub personal access token                          | `$GITHUB_TOKEN` |
| `--output`, `-o` | Output directory for reports                          | `./reports`     |
| `--json`, `-j`   | Also export raw API data as JSON                      | off             |
| `--graph`, `-g`  | Generate knowledge graph + LLM context document       | off             |
| `--max-files`    | Max source files to fetch for graph (default: 250)    | 250             |
| `--deepseek-key` | DeepSeek API key for AI-powered summary               | `$DEEPSEEK_API_KEY` |
| `--no-ai`        | Skip AI summary generation                            | off             |

---

## 💡 Sample Usage

### Basic report
```bash
python repo_report.py torvalds/linux
```

### Full URL with auth token
```bash
python repo_report.py https://github.com/pallets/flask --token ghp_xxxx
```

### Everything enabled (report + JSON + graph + AI summary)
```bash
python repo_report.py vercel/next.js \
  --token ghp_xxxx \
  --json \
  --graph \
  --output ./my-reports
```

### Graph only, skip AI summary
```bash
python repo_report.py facebook/react --graph --no-ai --token $(gh auth token)
```

### Using environment variables (no flags needed)
```bash
export GITHUB_TOKEN=ghp_xxxx
export DEEPSEEK_API_KEY=sk-xxxx
python repo_report.py django/django --graph --json
```

### Output files generated
```
./reports/
├── django_django_report.md      # Full markdown report with all sections
├── django_django_data.json      # Raw API data (with --json)
├── django_django_graph.json     # Dependency graph as JSON (with --graph)
└── django_django_context.txt    # LLM-ready context document (with --graph)
```

---

## 📊 What's in the Report?

### Core Sections
| Section                       | Details                                              |
|------------------------------ |----------------------------------------------------- |
| 🏆 Health Score + TL;DR       | 0–100 score across 6 dimensions + AI summary         |
| 🤖 AI Executive Summary      | DeepSeek-powered analysis of strengths & weaknesses  |
| 📋 Overview                  | Description, URL, visibility, dates                  |
| ⭐ Statistics                 | Stars, forks, watchers, issues, repo size            |
| 🏷️ Topics                    | Repository topics                                    |
| 💻 Languages                 | Byte-count breakdown with visual bars                |
| 📜 License                   | License name + SPDX ID                               |
| 👤 Owner                     | Username, type, avatar                               |
| 👥 Top Contributors          | Top 20 contributors with commit counts               |
| 📈 Commit Activity           | Weekly commit heatmap (last 12 weeks)                |
| 📉 Code Frequency            | Lines added/removed over time                        |
| ⏱️ Issue/PR Velocity         | Avg/median close times, PR merge rate                |
| 🌿 Branches                  | All branches with protection status                  |
| 🏷️ Tags / 🚀 Releases       | Tags + releases with assets & notes                  |
| 📝 Recent Commits            | Last 15 commits with SHA, message, author            |
| 🐛 Issues / 🔀 PRs           | Open issues and pull requests                        |
| ⚙️ GitHub Actions            | CI/CD workflows with states                          |
| 🤝 Community Profile         | Health checklist (CoC, Contributing, etc.)            |
| 📦 Dependencies              | Auto-detected build systems & dep files              |
| 🌐 Deployments / 📊 Traffic  | Recent deploys + view/clone stats                    |
| 📂 Directory Tree             | Full file tree of the repository                     |
| 📖 README Preview            | First 3000 chars of the README                       |

### Graph Outputs (with `--graph`)
| Output                        | Details                                              |
|------------------------------ |----------------------------------------------------- |
| 🕸️ Mermaid Diagram           | Visual dependency graph in the report                |
| 🗂️ JSON Graph                | `{nodes, edges, stats}` — machine-readable           |
| 📝 LLM Context Document      | Architecture overview, definitions, dependency map   |

---

## 🔑 Authentication

| Method                         | Rate Limit   |
|------------------------------- |------------- |
| No token                      | 60 req/hr    |
| With `--token` or `$GITHUB_TOKEN` | 5,000 req/hr |

```bash
# Use gh CLI
python repo_report.py owner/repo --token $(gh auth token)

# Or set env var
export GITHUB_TOKEN=ghp_xxxx
```

---

## 📁 Project Structure

```
Repo-Vector-Base/
├── repo_report.py       # Main CLI — fetches data & builds markdown
├── features.py          # Analysis features (parallel, retry, velocity, health, AI)
├── graph.py             # Knowledge graph (import parsing, Mermaid, LLM context)
├── requirements.txt     # Python dependencies
├── .env.example         # Template for API keys
├── .gitignore           # Ignores reports/, .env, __pycache__/
└── readme.md            # This file
```

---

## 📄 License

MIT
