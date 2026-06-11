#!/usr/bin/env python3
"""Discover which ATS each company uses, by probing public APIs.

Reads companies.txt (one name per line), tries token guesses against
Greenhouse / Ashby / Lever / SmartRecruiters, and records the first match.
Companies matching none use their own / other system (= the "B.5" list that
Claude Cowork will handle).

Output: ats-map.json
Run:    python3 discover_ats.py
Stdlib only.
"""
import concurrent.futures as cf
import json
import re
import sys
import urllib.request
import urllib.error

ROOT = __file__.rsplit("/", 2)[0]   # project root (scripts/ is one level down)
TIMEOUT = 8
SUFFIXES = {"inc", "corp", "corporation", "co", "company", "technologies",
            "technology", "group", "holdings", "financial", "labs", "lab",
            "ai", "systems", "international", "the", "and", "plc", "ltd",
            "motors", "pharmaceuticals", "bank", "capital", "trading"}


def slugify(name):
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", name.lower()))


def token_candidates(name):
    """Generate plausible ATS tokens for a company name."""
    cands = []
    def add(x):
        x = x.strip()
        if x and x not in cands:
            cands.append(x)

    slug = slugify(name)
    nospace = re.sub(r"[^a-z0-9]", "", name.lower())
    add(slug)
    add(nospace)
    # split on separators / parentheses: "Anysphere (Cursor)" -> anysphere, cursor
    parts = [p for p in re.split(r"[^a-z0-9]+", name.lower()) if p]
    if parts:
        add(parts[0])
    # drop trailing suffix words: "Arista Networks" -> arista
    core = [p for p in parts if p not in SUFFIXES]
    if core:
        add("".join(core))
        add("-".join(core))
        add(core[0])
    return cands[:6]


def _get(url, method="GET", data=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", "Mozilla/5.0 (job-board-fetcher)")
    if data is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(data).encode()
    with urllib.request.urlopen(req, data=data, timeout=TIMEOUT) as r:
        return r.status, r.read()


def try_json(url):
    try:
        status, body = _get(url)
        if status != 200:
            return None
        return json.loads(body)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError,
            TimeoutError, ConnectionError, OSError):
        return None


def probe_greenhouse(tok):
    d = try_json(f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs")
    if d and isinstance(d.get("jobs"), list) and len(d["jobs"]) > 0:
        return len(d["jobs"])
    return None


def probe_ashby(tok):
    d = try_json(f"https://api.ashbyhq.com/posting-api/job-board/{tok}")
    if d and isinstance(d.get("jobs"), list) and len(d["jobs"]) > 0:
        return len(d["jobs"])
    return None


def probe_lever(tok):
    d = try_json(f"https://api.lever.co/v0/postings/{tok}?mode=json")
    if isinstance(d, list) and len(d) > 0:
        return len(d)
    return None


def probe_smartrecruiters(tok):
    d = try_json(f"https://api.smartrecruiters.com/v1/companies/{tok}/postings?limit=10")
    if d and isinstance(d.get("content"), list) and d.get("totalFound", 0) > 0:
        return d["totalFound"]
    return None


PROBES = [
    ("greenhouse", probe_greenhouse, lambda c: c),                 # lowercase tokens
    ("ashby", probe_ashby, lambda c: c),
    ("lever", probe_lever, lambda c: c),
    # SmartRecruiters ids are often CamelCase: also try the raw no-space name
    ("smartrecruiters", probe_smartrecruiters, lambda c: c),
]


def classify(name):
    cands = token_candidates(name)
    sr_extra = [re.sub(r"[^A-Za-z0-9]", "", name)]  # CamelCase as-is, e.g. "Visa"
    for ats, fn, _ in PROBES:
        pool = cands + (sr_extra if ats == "smartrecruiters" else [])
        for tok in pool:
            n = fn(tok)
            if n:
                return {"name": name, "slug": slugify(name), "system": ats,
                        "token": tok, "postings_seen": n}
    return {"name": name, "slug": slugify(name), "system": "other",
            "token": None, "postings_seen": 0}


def main():
    with open(f"{ROOT}/data/companies.txt", encoding="utf-8") as f:
        names = [l.strip() for l in f if l.strip()]

    results = {}
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(classify, n): n for n in names}
        done = 0
        for fut in cf.as_completed(futs):
            r = fut.result()
            results[r["slug"]] = r
            done += 1
            mark = r["system"] if r["system"] != "other" else "·"
            print(f"  [{done}/{len(names)}] {r['name']:<28} -> {mark}", file=sys.stderr)

    # order by original company order
    ordered = {slugify(n): results[slugify(n)] for n in names}
    summary = {}
    for r in ordered.values():
        summary[r["system"]] = summary.get(r["system"], 0) + 1

    out = {"generated": "2026-06-03", "count": len(ordered),
           "summary": summary,
           "note": "system=greenhouse/lever/ashby/smartrecruiters -> fetcher 自動抓; "
                   "system=other -> 有自己/其他招募系統(Workday/iCIMS/in-house...)，交給 Cowork (B.5/C 層)。",
           "companies": ordered}
    with open(f"{ROOT}/data/ats-map.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nSUMMARY:", json.dumps(summary), file=sys.stderr)
    print("wrote ats-map.json", file=sys.stderr)


if __name__ == "__main__":
    main()
