#!/usr/bin/env python3
"""Merge browser/manually-found jobs into results/{slug}.json.

Used by the scheduled refresh skill: when Cowork finds a job on LinkedIn or a
company's own careers site that fetch_jobs.py didn't pick up, pipe it through here
instead of hand-editing JSON. Guarantees the data contract, a stable manual
job_id, dedup against what's already there, and preserved `applied` flags.

Input (file arg or stdin) — one company object, or a list of them:
{
  "company": "Google", "slug": "google",          // slug optional (derived)
  "source": "https://www.linkedin.com/jobs/...",   // where you found them
  "jobs": [
    {"title": "...", "locations": ["Mountain View, CA"],
     "apply_url": "https://...", "posted_date": "2026-06-01" | null,
     "job_board": "LinkedIn",                        // or "Company careers"
     "employment_type": "Full time", "qualifications": null,
     "salary_range": null, "sponsorship_note": null}
  ]
}

Run:  python3 add_jobs.py new_jobs.json
      cat new_jobs.json | python3 add_jobs.py
Stdlib only.
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
RESULTS = os.path.join(ROOT, "results")


def slugify(name):
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", (name or "").lower()))


def norm_url(u):
    return (u or "").rstrip("/").lower()


def manual_id(slug, title, url):
    h = hashlib.md5(f"{title}|{url}".encode("utf-8")).hexdigest()[:10]
    return f"{slug}-manual-{h}"


def merge_company(block, now):
    name = block.get("company")
    slug = block.get("slug") or slugify(name)
    if not slug:
        print("  skip: no company/slug", file=sys.stderr)
        return 0
    path = os.path.join(RESULTS, f"{slug}.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    else:
        doc = {"company": name or slug, "slug": slug, "fetched_at": now,
               "source": block.get("source"), "job_count": 0, "jobs": []}

    have = {norm_url(j.get("apply_url")) for j in doc["jobs"]}
    added = 0
    for nj in block.get("jobs", []):
        url = nj.get("apply_url")
        if not url or norm_url(url) in have:
            continue                       # dedup against everything already there
        have.add(norm_url(url))
        title = nj.get("title") or "(untitled)"
        doc["jobs"].append({
            "job_id": nj.get("job_id") or manual_id(slug, title, url),
            "title": title,
            "locations": nj.get("locations") or [],
            "apply_url": url,
            "posted_date": nj.get("posted_date"),
            "employment_type": nj.get("employment_type") or "Full time",
            "qualifications": nj.get("qualifications"),
            "salary_range": nj.get("salary_range"),
            "sponsorship_note": nj.get("sponsorship_note"),
            "job_board": nj.get("job_board") or "Company careers",
            "fetched_at": now,
            "applied": bool(nj.get("applied", False)),
            "screened": bool(nj.get("screened", False)),
        })
        added += 1

    doc["company"] = doc.get("company") or name or slug
    doc["slug"] = slug
    doc["fetched_at"] = now
    doc["job_count"] = len(doc["jobs"])
    os.makedirs(RESULTS, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    print(f"  {doc['company']:<28} +{added} (total {doc['job_count']})", file=sys.stderr)
    return added


def main():
    raw = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 \
        else sys.stdin.read()
    data = json.loads(raw)
    blocks = data if isinstance(data, list) else [data]
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    total = sum(merge_company(b, now) for b in blocks)
    print(f"added {total} new jobs across {len(blocks)} company block(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
