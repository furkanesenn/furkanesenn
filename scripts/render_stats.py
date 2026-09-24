"""Render the committed aggregate snapshot as a self-hosted GitHub profile card."""

import json
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COLORS = ["#58a6ff", "#3fb950", "#d2a8ff", "#f2cc60", "#ff7b72", "#79c0ff", "#a5a5a5"]


def render() -> None:
    data = json.loads((ROOT / "stats.json").read_text(encoding="utf-8"))
    year = data["as_of"][:4]
    rounded_contributions = f'~{data["contributions_2021_to_date"] / 1000:.0f}K'
    values = [
        (rounded_contributions, "GITHUB CONTRIBUTIONS", f"2021–{year} · rounded"),
        (f'{data["authored_commits_searchable"]:,}', "AUTHORED COMMITS", "searchable history"),
        (f'{data["current_project_code_lines"]:,}', "ACCESSIBLE PROJECT LOC", f'{data["code_repositories"]} repositories*'),
    ]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="370" viewBox="0 0 900 370" role="img" aria-label="Furkan Esen GitHub statistics">',
        '<rect width="900" height="370" rx="18" fill="#0d1117"/>',
        '<rect x="1" y="1" width="898" height="368" rx="17" fill="none" stroke="#30363d"/>',
        '<text x="30" y="42" fill="#f0f6fc" font-family="Segoe UI,Arial,sans-serif" font-size="23" font-weight="700">GitHub activity</text>',
        f'<text x="870" y="41" fill="#8b949e" font-family="Segoe UI,Arial,sans-serif" font-size="13" text-anchor="end">as of {escape(data["as_of"])}</text>',
    ]
    for index, (value, label, sublabel) in enumerate(values):
        x = 30 + index * 284
        parts += [
            f'<rect x="{x}" y="66" width="270" height="113" rx="12" fill="#161b22" stroke="#30363d"/>',
            f'<text x="{x+18}" y="111" fill="#f0f6fc" font-family="Segoe UI,Arial,sans-serif" font-size="32" font-weight="700">{escape(value)}</text>',
            f'<text x="{x+18}" y="139" fill="#58a6ff" font-family="Segoe UI,Arial,sans-serif" font-size="12" font-weight="700" letter-spacing="1">{escape(label)}</text>',
            f'<text x="{x+18}" y="161" fill="#8b949e" font-family="Segoe UI,Arial,sans-serif" font-size="12">{escape(sublabel)}</text>',
        ]
    parts.append('<text x="30" y="217" fill="#f0f6fc" font-family="Segoe UI,Arial,sans-serif" font-size="17" font-weight="600">Current project language mix</text>')
    languages = list(data["languages_by_current_code_lines"].items())[:6]
    total = sum(data["languages_by_current_code_lines"].values())
    x = 30
    for index, (_, count) in enumerate(languages):
        width = 840 * count / total
        parts.append(f'<rect x="{x:.1f}" y="232" width="{width:.1f}" height="15" fill="{COLORS[index]}"/>')
        x += width
    for index, (name, count) in enumerate(languages):
        col = index % 3
        row = index // 3
        x = 30 + col * 284
        y = 280 + row * 29
        share = count / total * 100
        parts += [
            f'<circle cx="{x+6}" cy="{y-4}" r="6" fill="{COLORS[index]}"/>',
            f'<text x="{x+19}" y="{y}" fill="#c9d1d9" font-family="Segoe UI,Arial,sans-serif" font-size="14">{escape(name)} · {share:.0f}%</text>',
        ]
    parts.append('<text x="30" y="351" fill="#8b949e" font-family="Segoe UI,Arial,sans-serif" font-size="11">*Current code lines across accessible repositories; includes team code. Private repository names stay private.</text>')
    parts.append('</svg>')
    output = ROOT / "stats" / "profile-stats.svg"
    output.parent.mkdir(exist_ok=True)
    output.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    render()
