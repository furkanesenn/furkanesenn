"""Summarize technologies in accessible GitHub repositories.

Only aggregate names are printed. Private repository names and manifest contents
are never written to the profile repository.
"""

from __future__ import annotations

import base64
import concurrent.futures
import http.client
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter


TOKEN = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "furkanesenn-tech-inventory",
    "X-GitHub-Api-Version": "2022-11-28",
}
MANIFESTS = ("package.json", "requirements.txt", "pyproject.toml", "go.mod", "pubspec.yaml", "composer.json", "Cargo.toml", "Dockerfile", "schema.prisma")
SKIP_DIRS = {"node_modules", "vendor", ".next", "dist", "build", ".venv", "venv", "target", "out", "tests", "test"}


def get(path: str) -> dict | list:
    request = urllib.request.Request("https://api.github.com/" + path.lstrip("/"), headers=HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in {404, 409, 422}:
                return {}
            if attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError, http.client.IncompleteRead):
            if attempt == 2:
                return {}
    return {}


def list_repos() -> list[dict]:
    repos = []
    page = 1
    while True:
        query = urllib.parse.urlencode({"affiliation": "owner,collaborator,organization_member", "per_page": 100, "page": page})
        batch = get("user/repos?" + query)
        repos.extend(batch)
        if len(batch) < 100:
            return repos
        page += 1


def manifests_for(repo: dict) -> list[tuple[str, str]]:
    if repo["fork"] or repo.get("disabled") or not repo.get("default_branch"):
        return []
    name = repo["full_name"]
    branch = urllib.parse.quote(repo["default_branch"], safe="")
    tree = get(f"repos/{name}/git/trees/{branch}?recursive=1")
    selected = []
    for item in tree.get("tree", []):
        path = item.get("path", "")
        if item.get("type") != "blob" or item.get("size", 0) > 200_000:
            continue
        parts = path.split("/")
        if any(part in SKIP_DIRS for part in parts[:-1]):
            continue
        if parts[-1] not in MANIFESTS:
            continue
        selected.append((name, parts[-1], item["sha"]))
    results = []
    for name, kind, sha in selected:
        blob = get(f"repos/{name}/git/blobs/{sha}")
        if blob.get("encoding") == "base64":
            results.append((kind, base64.b64decode(blob["content"]).decode("utf-8", errors="replace")))
    return results


def main() -> None:
    repos = list_repos()
    packages: Counter[str] = Counter()
    manifests: Counter[str] = Counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for files in pool.map(manifests_for, repos):
            for kind, content in files:
                manifests[kind] += 1
                if kind in {"package.json", "composer.json"}:
                    try:
                        data = json.loads(content)
                    except json.JSONDecodeError:
                        continue
                    for group in ("dependencies", "devDependencies", "require", "require-dev"):
                        packages.update(data.get(group, {}).keys())
                elif kind == "requirements.txt":
                    for line in content.splitlines():
                        match = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*(?:[=<>!~;\[]|$)", line)
                        if match:
                            packages[match.group(1).lower()] += 1
                elif kind == "pubspec.yaml":
                    for match in re.finditer(r"(?m)^  ([A-Za-z0-9_]+):", content):
                        packages[match.group(1)] += 1
                elif kind == "pyproject.toml":
                    try:
                        import tomllib
                        data = tomllib.loads(content)
                        for package in data.get("project", {}).get("dependencies", []):
                            match = re.match(r"([A-Za-z0-9_.-]+)", package)
                            if match:
                                packages[match.group(1).lower()] += 1
                    except (ImportError, ValueError):
                        pass
    print(json.dumps({"accessible_repositories": len(repos), "manifest_counts": manifests, "packages": packages.most_common()}, indent=2))


if __name__ == "__main__":
    main()
