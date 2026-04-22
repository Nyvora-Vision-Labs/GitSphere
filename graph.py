#!/usr/bin/env python3
"""
graph.py — Repository Knowledge Graph Generator
"""

import base64
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ──────────────────────────────────────────────
# Import Parsers (multi-language)
# ──────────────────────────────────────────────
IMPORT_PATTERNS = {
    ".py": [
        (r'^import\s+([\w.]+)', "module"),
        (r'^from\s+([\w.]+)\s+import', "module"),
    ],
    ".js": [
        (r'(?:import|export)\s+.*?from\s+[\'"]([^"\']+)[\'"]', "path"),
        (r'require\s*\(\s*[\'"]([^"\']+)[\'"]\s*\)', "path"),
    ],
    ".ts": [
        (r'(?:import|export)\s+.*?from\s+[\'"]([^"\']+)[\'"]', "path"),
        (r'require\s*\(\s*[\'"]([^"\']+)[\'"]\s*\)', "path"),
    ],
    ".tsx": [
        (r'(?:import|export)\s+.*?from\s+[\'"]([^"\']+)[\'"]', "path"),
    ],
    ".jsx": [
        (r'(?:import|export)\s+.*?from\s+[\'"]([^"\']+)[\'"]', "path"),
    ],
    ".go": [
        (r'"([^"]+)"', "path"),
    ],
    ".rs": [
        (r'(?:use|mod)\s+([\w:]+)', "module"),
        (r'extern\s+crate\s+(\w+)', "module"),
    ],
    ".java": [
        (r'^import\s+([\w.]+)', "module"),
    ],
    ".rb": [
        (r"require\s+['\"]([^'\"]+)['\"]", "path"),
        (r"require_relative\s+['\"]([^'\"]+)['\"]", "path"),
    ],
    ".c": [
        (r'#include\s*[<"]([^>"]+)[>"]', "path"),
    ],
    ".h": [
        (r'#include\s*[<"]([^>"]+)[>"]', "path"),
    ],
    ".cpp": [
        (r'#include\s*[<"]([^>"]+)[>"]', "path"),
    ],
    ".swift": [
        (r'^import\s+(\w+)', "module"),
    ],
}

SOURCE_EXTENSIONS = set(IMPORT_PATTERNS.keys())

SKIP_PATTERNS = [
    "node_modules/", "vendor/", "dist/", "build/", ".min.",
    "__pycache__/", ".pyc", "venv/", ".venv/",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".ttf", ".eot", ".mp3", ".mp4",
    ".zip", ".tar", ".gz", ".jar", ".exe",
    "package-lock.json", "yarn.lock", "Pipfile.lock",
    "go.sum", "Cargo.lock",
]

PRIORITY_FILES = [
    "package.json", "pyproject.toml", "setup.py", "setup.cfg",
    "Cargo.toml", "go.mod", "Gemfile", "composer.json",
    "pom.xml", "build.gradle", "Makefile", "Dockerfile",
    "docker-compose.yml", "docker-compose.yaml",
    ".github/workflows/", "tsconfig.json", "vite.config",
    "webpack.config", "next.config", "tailwind.config",
]

ENTRY_INDICATORS = {
    "main.py", "app.py", "__main__.py", "index.js", "index.ts",
    "main.go", "main.rs", "Main.java", "server.py", "server.js",
    "cli.py", "manage.py", "wsgi.py", "asgi.py",
}

CONFIG_FILE_NAMES = {
    "package.json", "pyproject.toml", "setup.py", "setup.cfg",
    "Cargo.toml", "go.mod", "Gemfile", "composer.json",
    "pom.xml", "build.gradle", "Makefile", "Dockerfile",
    "docker-compose.yml", "docker-compose.yaml",
    "tsconfig.json", "vite.config", "webpack.config", "next.config",
    "tailwind.config.js", "tailwind.config.ts", "tailwind.config.cjs",
}

WRAPPER_DIRS = {
    "src", "lib", "app", "apps", "packages", "services",
    "modules", "internal", "components", "cmd",
}

def should_skip(path):
    return any(skip in path for skip in SKIP_PATTERNS)

def is_source_file(path):
    return any(path.endswith(ext) for ext in SOURCE_EXTENSIONS)

def is_priority_file(path):
    return any(p in path for p in PRIORITY_FILES)

def path_directory(path):
    return path.rsplit("/", 1)[0] if "/" in path else ""

def classify_file_role(path, is_entry_point=False):
    name = path.split("/")[-1]
    lower_path = path.lower()

    if is_entry_point or name in ENTRY_INDICATORS:
        return "entry"
    if lower_path.startswith(".github/workflows/"):
        return "automation"
    if (
        "/tests/" in lower_path or lower_path.startswith("tests/")
        or "/test/" in lower_path or lower_path.startswith("test/")
        or "/__tests__/" in lower_path or name.endswith(".spec.js")
        or name.endswith(".spec.ts") or name.endswith(".test.js")
        or name.endswith(".test.ts") or name.endswith("_test.go")
        or name.startswith("test_")
    ):
        return "test"
    if name in CONFIG_FILE_NAMES or "/config/" in lower_path or lower_path.endswith(".env.example"):
        return "config"
    if lower_path.startswith("docs/") or name.lower().startswith("readme") or lower_path.endswith((".md", ".rst", ".txt")):
        return "docs"
    return "source"

def derive_module_id(path, node_type="file"):
    if path == ".": return "."
    parts = path.split("/")
    directory_parts = parts if node_type == "directory" else parts[:-1]
    if not directory_parts: return "."
    if directory_parts[0] in WRAPPER_DIRS and len(directory_parts) >= 2:
        return "/".join(directory_parts[:2])
    return directory_parts[0]

def ai_prune_tree(paths, repo_desc="", api_key=None):
    """Uses AI to identify core files from a large list of paths."""
    if not api_key or not paths:
        return paths

    from features import call_deepseek_api
    
    # Truncate paths list to avoid token overflow
    max_paths = 600
    pruned_input = paths[:max_paths]
    
    prompt = f"""
    Analyze the file paths for the repository '{repo_desc}'.
    Select ONLY the most critical files that form the "DNA" of this project.
    
    These are the minimal set of files required for a developer to understand the core logic 
    and recreate the project's functionality from scratch.
    
    Focus on:
    - Primary entry points and bootstrap files.
    - Core logic, algorithms, and business rules.
    - Main data models and API definitions.
    - Essential configuration that defines the project structure.
    
    STRICTLY IGNORE:
    - boilerplate, tests, docs, assets, and minor utilities.
    
    RETURN ONLY a JSON array of the paths. No preamble.
    
    PATHS:
    {json.dumps(pruned_input)}
    """
    
    print("🤖  AI is identifying core repository files…")
    result = call_deepseek_api(prompt, api_key)
    
    if result:
        try:
            # Clean up potential markdown formatting in AI response
            clean_result = re.search(r'\[.*\]', result, re.DOTALL)
            if clean_result:
                ai_selected = json.loads(clean_result.group(0))
                # Validate selected paths actually exist in our original list
                valid_paths = [p for p in ai_selected if p in paths]
                if valid_paths:
                    print(f"✨ AI selected {len(valid_paths)} core files (from {len(paths)} candidates)")
                    return valid_paths
        except Exception as e:
            print(f"⚠️  AI pruning failed to parse: {e}")
            
    return paths

def human_module_name(module_id):
    return "(root files)" if module_id == "." else module_id

def fetch_file_contents(session, owner, repo, tree, max_files=250, deepseek_key=None):
    base = f"/repos/{owner}/{repo}/contents"
    repo_desc = "" # Optionally fetch if needed
    
    files_to_fetch = []
    for item in tree:
        if item.get("type") != "blob": continue
        path = item.get("path", "")
        if should_skip(path): continue
        if item.get("size", 0) > 100_000: continue
        if is_source_file(path) or is_priority_file(path):
            files_to_fetch.append(path)

    # 1. AI Pruning (if enabled)
    if deepseek_key and len(files_to_fetch) > 20:
        files_to_fetch = ai_prune_tree(files_to_fetch, f"{owner}/{repo}", deepseek_key)

    # 2. Hard Truncation (Safety)
    if len(files_to_fetch) > max_files:
        priority = [f for f in files_to_fetch if is_priority_file(f)]
        source = [f for f in files_to_fetch if not is_priority_file(f)]
        source.sort(key=lambda p: p.count("/")) 
        files_to_fetch = priority + source[:max_files - len(priority)]

    print(f"📡  Fetching {len(files_to_fetch)} source files for graph analysis…")
    file_contents = {}

    def fetch_one(path):
        from features import api_get_retry
        data = api_get_retry(session, f"{base}/{path}")
        if data and data.get("content"):
            try:
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                return path, content
            except Exception: pass
        return path, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_one, path) for path in files_to_fetch]
        for future in as_completed(futures):
            try:
                path, content = future.result()
                if content is not None:
                    file_contents[path] = content
            except Exception: pass

    return file_contents

def parse_imports(path, content):
    ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
    patterns = IMPORT_PATTERNS.get(ext, [])
    if not patterns: return []

    imports = []
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"): continue
        for pattern, import_type in patterns:
            matches = re.findall(pattern, line)
            for match in matches:
                imports.append({"raw": match, "type": import_type})
    return imports

def parse_definitions(path, content):
    defs = []
    ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""

    if ext == ".py":
        for match in re.finditer(r'^class\s+(\w+)', content, re.MULTILINE):
            defs.append({"type": "class", "name": match.group(1)})
        for match in re.finditer(r'^def\s+(\w+)', content, re.MULTILINE):
            defs.append({"type": "function", "name": match.group(1)})
    elif ext in (".js", ".ts", ".jsx", ".tsx"):
        for match in re.finditer(r'(?:export\s+)?(?:default\s+)?class\s+(\w+)', content):
            defs.append({"type": "class", "name": match.group(1)})
        for match in re.finditer(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)', content):
            defs.append({"type": "function", "name": match.group(1)})
    elif ext == ".go":
        for match in re.finditer(r'^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)', content, re.MULTILINE):
            defs.append({"type": "function", "name": match.group(1)})
    elif ext == ".java":
        for match in re.finditer(r'(?:public|private|protected)?\s*class\s+(\w+)', content):
            defs.append({"type": "class", "name": match.group(1)})

    return defs

def resolve_import(importing_file, raw_import, import_type, all_paths):
    if import_type == "module":
        candidates = [
            raw_import.replace(".", "/") + ".py",
            raw_import.replace(".", "/") + "/__init__.py",
            "src/" + raw_import.replace(".", "/") + ".py",
            "lib/" + raw_import.replace(".", "/") + ".py",
        ]
    else:
        dir_of_file = "/".join(importing_file.split("/")[:-1])
        clean = raw_import
        if clean.startswith("./"): clean = clean[2:]
        elif clean.startswith("../"):
            parts = dir_of_file.split("/")
            while clean.startswith("../"):
                clean = clean[3:]
                if parts: parts.pop()
            dir_of_file = "/".join(parts)

        if clean.startswith("@") or clean.startswith("~"): return None

        base = f"{dir_of_file}/{clean}" if dir_of_file else clean
        candidates = [
            base,
            base + ".py", base + ".js", base + ".ts", base + ".tsx",
            base + "/index.js", base + "/index.ts", base + "/__init__.py",
        ]

    for candidate in candidates:
        normalized = candidate.lstrip("/")
        if normalized in all_paths: return normalized
    return None

def build_graph(file_contents, tree):
    """Builds a 'Powerful' Knowledge Graph with 100% connectivity."""
    all_paths = {item["path"] for item in tree if item.get("type") == "blob"}
    nodes = {}
    edges = []
    seen_edges = set()

    def add_edge(src, dst, edge_type, raw=None):
        key = (src, dst, edge_type)
        if key not in seen_edges:
            seen_edges.add(key)
            edge = {"from": src, "to": dst, "type": edge_type}
            if raw: edge["raw"] = raw
            edges.append(edge)

    # 1. Create Virtual Root for absolute connectivity
    nodes["."] = {
        "id": ".",
        "type": "directory",
        "name": "(root)",
        "importance_score": 10
    }

    # 2. Build Nodes and Synthesize Directory Hierarchy
    all_dirs = set()
    for item in tree:
        path = item.get("path", "")
        if item.get("type") == "tree": continue
        if should_skip(path): continue
        
        ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
        is_entry = path.split("/")[-1] in ENTRY_INDICATORS
        
        nodes[path] = {
            "id": path,
            "type": "file",
            "name": path.split("/")[-1],
            "extension": ext,
            "role": classify_file_role(path, is_entry),
            "is_entry_point": is_entry,
            "size": item.get("size", 0)
        }
        
        if path in file_contents:
            content = file_contents[path]
            nodes[path]["definitions"] = parse_definitions(path, content)
            nodes[path]["imports_raw"] = parse_imports(path, content)
            nodes[path]["lines"] = content.count("\n") + 1
            
        parts = path.split("/")
        for depth in range(1, len(parts)):
            d = "/".join(parts[:depth])
            if not should_skip(d):
                all_dirs.add(d)

    # 3. Create Directory Nodes
    for dir_path in all_dirs:
        if dir_path not in nodes:
            nodes[dir_path] = {
                "id": dir_path,
                "type": "directory",
                "name": dir_path.split("/")[-1]
            }

    # 4. Connect Structure (Containment Edges)
    for path in list(nodes.keys()):
        if path == ".": continue
        parts = path.split("/")
        parent = "/".join(parts[:-1]) if len(parts) > 1 else "."
        add_edge(parent, path, "contains")

    # 5. Connect Logic (Import Edges)
    for path, content in file_contents.items():
        imports = parse_imports(path, content)
        for imp in imports:
            resolved = resolve_import(path, imp["raw"], imp["type"], all_paths)
            if resolved and resolved != path:
                add_edge(path, resolved, "imports", raw=imp["raw"])

    return {"nodes": nodes, "edges": edges}

# --- Export and Utility Functions Below ---
# (Keeping JSON structuring identical to original but utilizing new metadata)

def build_graph_export(graph, owner, repo):
    export = {
        "repository": f"{owner}/{repo}",
        "schema_version": 2,
        "default_view": "overview",
        "nodes": [],
        "edges": [],
        "views": {},
        "stats": {},
    }

    import_outbound = defaultdict(int)
    import_inbound = defaultdict(int)
    for edge in graph["edges"]:
        if edge["type"] == "imports":
            import_outbound[edge["from"]] += 1
            import_inbound[edge["to"]] += 1

    for path, node in graph["nodes"].items():
        clean_node = dict(node)
        clean_node["module"] = derive_module_id(path, node_type=node["type"])
        
        if node["type"] == "file":
            inbound = import_inbound.get(path, 0)
            outbound = import_outbound.get(path, 0)
            clean_node["inbound_imports"] = inbound
            clean_node["outbound_imports"] = outbound
            clean_node["import_degree"] = inbound + outbound
            
            # Semantic Scoring
            clean_node["importance_score"] = (
                (8 if clean_node.get("is_entry_point") else 0)
                + (4 if clean_node.get("role") == "config" else 0)
                + (inbound * 2)
                + outbound
            )
        export["nodes"].append(clean_node)

    for edge in graph["edges"]:
        export["edges"].append(edge)

    export["stats"] = {
        "total_files": len([n for n in export["nodes"] if n["type"] == "file"]),
        "total_import_edges": len([e for e in export["edges"] if e["type"] == "imports"]),
        "entry_points": sorted(n["id"] for n in export["nodes"] if n.get("is_entry_point")),
    }
    return export

def export_graph_json(graph, output_dir, owner, repo):
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{owner}_{repo}_graph.json")
    export = build_graph_export(graph, owner, repo)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)
    return filepath