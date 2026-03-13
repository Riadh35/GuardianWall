#!/usr/bin/env python3
"""
Guardian Wall — Community Blacklist Processor
Runs hourly via GitHub Actions.

Reads open Issues labelled "spam-report", counts votes per number,
and writes community/numbers.json with numbers that have >= MIN_REPORTS votes.

One vote per GitHub user per number (deduplication by username).
Closing an Issue = vote retracted (only open issues are counted).
"""

import json
import os
import re
from datetime import datetime, timezone
from urllib.request import urlopen, Request

GH_TOKEN   = os.environ.get("GH_TOKEN", "")
REPO       = os.environ.get("REPO", "Riadh35/GuardianWall")
OUTPUT     = "community/numbers.json"
MIN_REPORTS = 1   # TEST — seuil temporaire à 1 vote (remettre à 2 en production)


def gh_get(path: str, params: str = "") -> list:
    """Paginated GitHub API GET — returns all items."""
    items = []
    page  = 1
    while True:
        url = f"https://api.github.com/{path}?per_page=100&page={page}{params}"
        req = Request(url, headers={
            "Authorization": f"Bearer {GH_TOKEN}",
            "Accept":        "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        with urlopen(req, timeout=15) as r:
            batch = json.loads(r.read())
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items


def parse_body(body: str) -> dict:
    """Extract key: value fields from issue body."""
    result = {}
    for line in (body or "").splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip().lower().replace(" ", "_")] = val.strip()
    return result


def normalize(raw: str) -> str:
    n = re.sub(r"[\s\-().]+", "", raw.strip())
    if n.startswith("+33") and len(n) == 12:
        n = "0" + n[3:]
    if n.startswith("0033") and len(n) == 13:
        n = "0" + n[4:]
    return n


def valid_number(n: str) -> bool:
    return bool(re.match(r"^(0[1-9]\d{8}|\+\d{10,14})$", n))


def main():
    print(f"Fetching open spam-report issues from {REPO}…")
    issues = gh_get(
        f"repos/{REPO}/issues",
        "&state=open&labels=spam-report"
    )
    print(f"  Found {len(issues)} open reports")

    # votes[number] = { users: set, category: str, danger_level: int }
    votes: dict = {}

    for issue in issues:
        user   = issue["user"]["login"]
        fields = parse_body(issue.get("body", ""))

        raw = fields.get("number", "").strip()
        if not raw:
            continue

        number = normalize(raw)
        if not number or not valid_number(number):
            print(f"  Skipping invalid number: {raw!r}")
            continue

        category     = fields.get("category", "Spam").strip() or "Spam"
        danger_level = int(fields.get("danger_level", "3").strip() or "3")
        danger_level = max(1, min(5, danger_level))

        if number not in votes:
            votes[number] = {
                "users":        set(),
                "category":     category,
                "danger_level": danger_level,
            }
        votes[number]["users"].add(user)

    # Build output — only numbers with enough votes
    numbers = []
    for number, data in votes.items():
        count = len(data["users"])
        if count >= MIN_REPORTS:
            numbers.append({
                "number":       number,
                "category":     data["category"],
                "danger_level": data["danger_level"],
                "reports":      count,
            })

    numbers.sort(key=lambda x: -x["reports"])

    output = {
        "version":    1,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "min_reports": MIN_REPORTS,
        "count":      len(numbers),
        "numbers":    numbers,
    }

    os.makedirs("community", exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_reports = sum(len(v["users"]) for v in votes.values())
    print(f"Written {OUTPUT}: {len(numbers)} numbers published "
          f"({total_reports} total reports, threshold={MIN_REPORTS})")


if __name__ == "__main__":
    main()
