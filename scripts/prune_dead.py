#!/usr/bin/env python3
"""Remove dead job postings from results/*.json.

Re-checks every job's apply_url and drops the ones that are definitively gone
(HTTP 404 / 410) so you never click through to an expired posting. Conservative
on purpose: anti-bot blocks (403/429/999), 5xx, timeouts and redirects are
treated as "still alive" — we only delete on an unambiguous not-found.

`applied` jobs are never auto-removed (you applied; keep the record) — they're
reported instead so you can decide.

Run:  python3 prune_dead.py            # apply removals
      python3 prune_dead.py --dry-run  # just report
Stdlib only.
"""
import concurrent.futures as cf
import glob
import json
import os
import sys
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
RESULTS = os.path.join(ROOT, "results")
TIMEOUT = 12
DEAD = {404, 410}


def status(url):
    """Return HTTP status, or None on network error/timeout (treat as alive)."""
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method)
            req.add_header("User-Agent", "Mozilla/5.0 (job-board-fetcher)")
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.status
        except urllib.error.HTTPError as e:
            if e.code == 405 and method == "HEAD":   # HEAD not allowed -> try GET
                continue
            return e.code
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            return None
    return None


def main():
    dry = "--dry-run" in sys.argv
    files = glob.glob(os.path.join(RESULTS, "*.json"))

    # gather all (file, job) pairs with a url
    jobs = []
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            doc = json.load(f)
        for j in doc.get("jobs", []):
            if j.get("apply_url"):
                jobs.append((fp, j["apply_url"]))

    codes = {}
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(status, u): u for _, u in jobs}
        for fut in cf.as_completed(futs):
            codes[futs[fut]] = fut.result()

    removed = kept_applied = 0
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            doc = json.load(f)
        keep = []
        for j in doc.get("jobs", []):
            code = codes.get(j.get("apply_url"))
            if code in DEAD:
                if j.get("applied"):
                    kept_applied += 1
                    keep.append(j)   # never silently drop something you applied to
                    print(f"  APPLIED but {code}: {doc['company']} - {j['title']}",
                          file=sys.stderr)
                else:
                    removed += 1
                    print(f"  dead {code}: {doc['company']} - {j['title']}",
                          file=sys.stderr)
                continue
            keep.append(j)
        if not dry and len(keep) != len(doc.get("jobs", [])):
            doc["jobs"] = keep
            doc["job_count"] = len(keep)
            tmp = fp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
            os.replace(tmp, fp)

    verb = "would remove" if dry else "removed"
    print(f"\n{verb} {removed} dead jobs; kept {kept_applied} dead-but-applied "
          f"(flagged above)", file=sys.stderr)


if __name__ == "__main__":
    main()
