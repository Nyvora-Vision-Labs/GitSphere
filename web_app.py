import os
from flask import Flask, request, jsonify, send_from_directory
from repo_report import build_session, parse_repo_input, build_markdown
from graph import fetch_file_contents, build_graph, build_graph_export
from features import fetch_all_parallel, summarize_with_ai

app = Flask(__name__, static_folder='.')

@app.route('/')
def index():
    return send_from_directory('.', 'viewer.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify({
        "server_credentials": {
            "github_token_configured": bool(os.environ.get("GITHUB_TOKEN")),
            "deepseek_key_configured": bool(os.environ.get("DEEPSEEK_API_KEY")),
        }
    })

@app.route('/api/repo-graph', methods=['POST'])
def generate_everything():
    try:
        payload = request.json
        repo_url = (payload.get("repo") or "").strip()
        if not repo_url:
            return jsonify({"error": "Repository is required."}), 400
            
        token = payload.get("github_token") or os.environ.get("GITHUB_TOKEN")
        deepseek_key = payload.get("deepseek_key") or os.environ.get("DEEPSEEK_API_KEY")
        max_files = int(payload.get("max_files", 250))
        
        owner, repo = parse_repo_input(repo_url)
        session = build_session(token)
        
        # 1. Fetch Repository Metadata (Pruned & Fast)
        repo_data = fetch_all_parallel(session, owner, repo)
        if not repo_data:
            return jsonify({"error": "Repository not found."}), 404
            
        # 2. Build the Knowledge Graph
        tree = repo_data.get("tree", [])
        contents = fetch_file_contents(
            session, owner, repo, tree, 
            max_files=max_files, 
            deepseek_key=deepseek_key
        )
        raw_graph = build_graph(contents, tree)
        final_json = build_graph_export(raw_graph, owner, repo)
        
        # 3. Optional AI Summary
        ai_summary = None
        ai_status = "skipped"
        if payload.get("include_ai_summary", True):
            if deepseek_key:
                ai_summary = summarize_with_ai(build_markdown(repo_data), api_key=deepseek_key)
                ai_status = "generated" if ai_summary else "failed"
            else:
                ai_status = "missing_key"

        # 4. Return UI Payload (Full Context)
        repo_info = repo_data.get("repo", {})
        languages = repo_data.get("languages") or {}
        
        from features import calculate_health_score
        health_score, _ = calculate_health_score(repo_data)
        
        def grade_for_score(score: int) -> str:
            if score >= 90: return "A+"
            if score >= 80: return "A"
            if score >= 70: return "B"
            if score >= 60: return "C"
            if score >= 50: return "D"
            return "F"

        return jsonify({
            "graph": final_json,
            "repo": {
                "full_name": repo_info.get("full_name", f"{owner}/{repo}"),
                "html_url": repo_info.get("html_url"),
                "description": repo_info.get("description", ""),
                "stars": repo_info.get("stargazers_count", 0),
                "forks": repo_info.get("forks_count", 0),
                "open_issues": repo_info.get("open_issues_count", 0),
                "health_score": health_score,
                "health_grade": grade_for_score(health_score),
                "languages": [
                    {"name": name, "bytes": size}
                    for name, size in sorted(languages.items(), key=lambda item: -item[1])[:5]
                ],
                "ai_summary": ai_summary,
                "ai_summary_status": ai_status,
                "stats": final_json.get('stats', {})
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("🌐 Repo-Vector-Base Flask app running at http://127.0.0.1:8000")
    app.run(port=8000, debug=True)