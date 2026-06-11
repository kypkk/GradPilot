#!/usr/bin/env python3
"""Merge a resume-screening result into screenings/screenings.json.

Used by the resume-screen skill so Cowork never hand-edits the JSON (which risks
clobbering other entries). Keyed by job_id, which joins to results/{slug}.json.

Input (file arg or stdin) — one entry or a list:
{
  "job_id": "amazon-smpl-bfa6…",        // must match the job in results/
  "company": "Amazon", "title": "Software Development Engineer",
  "profiles": {
    "backend-infra": {"badge":"pass","score":82,"knockouts":[],
                      "missing":["Kubernetes"],"fixes":["…"],
                      "report":"screenings/reports/amazon-smpl-bfa6…-backend-infra.md"},
    "ai-mlops":      {"badge":"knockout","score":40,
                      "knockouts":["US citizenship required"],"missing":[…],"fixes":[…]}
  }
}
badge ∈ {"pass","borderline","knockout"}.

Run: python3 save_screening.py entry.json   |   cat entry.json | python3 save_screening.py
Stdlib only.
"""
import json
import os
import sys
from datetime import datetime

import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
PATH = os.path.join(ROOT, "screenings", "screenings.json")
RESULTS = os.path.join(ROOT, "results")
VALID = {"pass", "borderline", "knockout"}


def mark_screened(job_ids):
    """Flip screened=true on the matching results/ jobs so the field stays in sync."""
    if not job_ids:
        return
    for fp in glob.glob(os.path.join(RESULTS, "*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                doc = json.load(f)
        except (ValueError, OSError):
            continue
        changed = False
        for j in doc.get("jobs", []):
            if j.get("job_id") in job_ids and not j.get("screened"):
                j["screened"] = True
                changed = True
        if changed:
            tmp = fp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
            os.replace(tmp, fp)


def main():
    raw = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 \
        else sys.stdin.read()
    data = json.loads(raw)
    entries = data if isinstance(data, list) else [data]

    if os.path.isfile(PATH):
        with open(PATH, encoding="utf-8") as f:
            doc = json.load(f)
    else:
        doc = {"screenings": {}}
    doc.setdefault("screenings", {})

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    n = 0
    done_ids = set()
    for e in entries:
        jid = e.get("job_id")
        if not jid:
            print("  skip: entry missing job_id", file=sys.stderr)
            continue
        profiles = e.get("profiles") or {}
        for key, p in profiles.items():
            if p.get("badge") not in VALID:
                print(f"  warn: {jid}/{key} badge={p.get('badge')!r} "
                      f"(expected one of {sorted(VALID)})", file=sys.stderr)
        doc["screenings"][jid] = {
            "company": e.get("company"),
            "title": e.get("title"),
            "screened_at": e.get("screened_at") or now,
            "profiles": profiles,
        }
        n += 1
        done_ids.add(jid)
        print(f"  screened {jid}: " +
              ", ".join(f"{k}={v.get('badge')}({v.get('score')})"
                        for k, v in profiles.items()), file=sys.stderr)

    mark_screened(done_ids)   # set screened=true on the matching results/ jobs
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)
    print(f"saved {n} screening(s); total now {len(doc['screenings'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
