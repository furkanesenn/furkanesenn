"""Build an aggregate GitHub profile snapshot from accessible project HEADs.

Requires `gh auth login` and the official cloc executable (set CLOC_BIN).
Only aggregate results are written. Private repository names and code stay local.
"""

from __future__ import annotations

import datetime as dt
import concurrent.futures
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOGIN = "furkanesenn"
EXCLUDED_DIRS = ".git,node_modules,vendor,dist,build,.next,coverage,.venv,venv,target,out"
EXCLUDED_EXTS = "md,txt,json,yaml,yml,svg,lock,toml,xml,csv"


def api(path: str, token: str, *, data: dict | None = None):
    url = "https://api.github.com/" + path.lstrip("/")
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "furkanesenn-profile-stats",
        "Content-Type": "application/json",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
    raise RuntimeError("GitHub API request failed")


def contribution_totals(token: str) -> tuple[int, int]:
    query = """query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) { contributionsCollection(from:$from,to:$to) {
        contributionCalendar { totalContributions }
        restrictedContributionsCount
      } }
    }"""
    today = dt.datetime.now(dt.timezone.utc).date()
    all_time = restricted = 0
    for year in range(2021, today.year + 1):
        end = min(dt.date(year, 12, 31), today)
        result = api("graphql", token, data={"query": query, "variables": {
            "login": LOGIN,
            "from": f"{year}-01-01T00:00:00Z",
            "to": f"{end.isoformat()}T23:59:59Z",
        }})
        if result.get("errors"):
            raise RuntimeError(result["errors"])
        collection = result["data"]["user"]["contributionsCollection"]
        all_time += collection["contributionCalendar"]["totalContributions"]
        restricted += collection["restrictedContributionsCount"]
    return all_time, restricted


def authored_commits_and_repos(token: str) -> tuple[int, dict[str, dict]]:
    first = api("search/commits?" + urllib.parse.urlencode({
        "q": f"author:{LOGIN}", "per_page": 100, "page": 1,
    }), token)
    total = first["total_count"]
    if total > 1000:
        raise RuntimeError("GitHub search caps results at 1,000; split by date")
    items = first["items"]
    for page in range(2, (total + 99) // 100 + 1):
        items += api("search/commits?" + urllib.parse.urlencode({
            "q": f"author:{LOGIN}", "per_page": 100, "page": page,
        }), token)["items"]
    repos = {item["repository"]["full_name"]: item["repository"] for item in items}
    # Also cover owned projects whose commits are not indexed by search.
    page = 1
    while True:
        owned = api("user/repos?" + urllib.parse.urlencode({
            "affiliation": "owner", "per_page": 100, "page": page,
        }), token)
        for repo in owned:
            if repo["owner"]["login"].lower() == LOGIN:
                repos[repo["full_name"]] = repo
        if len(owned) < 100:
            break
        page += 1
    return len({item["sha"] for item in items}), repos


def count_repo(repo: str, cloc: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="furkan-github-loc-") as temp:
        destination = Path(temp) / "project"
        subprocess.run(
            ["gh", "repo", "clone", repo, str(destination), "--", "--depth", "1", "--single-branch"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        result = subprocess.run([
            cloc, str(destination), "--json", "--quiet",
            f"--exclude-dir={EXCLUDED_DIRS}", f"--exclude-ext={EXCLUDED_EXTS}",
        ], check=True, capture_output=True, text=True)
        return json.loads(result.stdout)


def main() -> None:
    cloc = os.environ.get("CLOC_BIN") or shutil.which("cloc")
    if not cloc or not Path(cloc).exists():
        raise RuntimeError("Install official cloc and set CLOC_BIN to its executable path")
    token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    contributions, restricted = contribution_totals(token)
    authored_commits, repos = authored_commits_and_repos(token)
    selected = [repo for repo in repos.values() if not repo.get("fork") and not repo.get("disabled")]
    languages = Counter()
    code_repositories = 0
    private_repositories = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(count_repo, repo["full_name"], cloc): repo for repo in selected}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            repo = futures[future]
            result = future.result()
            print(f"Counted repository {index}/{len(selected)}", flush=True)
            total = result.get("SUM", {}).get("code", 0)
            if total:
                code_repositories += 1
                private_repositories += bool(repo["private"])
            for language, item in result.items():
                if language not in {"header", "SUM"} and isinstance(item, dict):
                    languages[language] += item.get("code", 0)
    snapshot = {
        "as_of": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        "contributions_2021_to_date": contributions,
        "restricted_contributions_2021_to_date": restricted,
        "authored_commits_searchable": authored_commits,
        "repositories_scanned": len(selected),
        "code_repositories": code_repositories,
        "private_code_repositories": private_repositories,
        "current_project_code_lines": sum(languages.values()),
        "languages_by_current_code_lines": dict(languages.most_common()),
    }
    (ROOT / "stats.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(snapshot, indent=2))


if __name__ == "__main__":
    main()
