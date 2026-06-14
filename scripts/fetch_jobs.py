#!/usr/bin/env python3
"""A + B layer new-grad SWE fetcher.

Sources:
  A. Simplify community new-grad listings.json (pre-filtered to new grad)
  B. Per-company ATS public APIs from ats-map.json:
     Greenhouse / Lever / Ashby / SmartRecruiters

Filters: software-engineering roles, new-grad level, US locations.
Writes results/{slug}.json per the project data contract, merging the existing
`applied` flag on re-fetch. Stdlib only.

Run: python3 fetch_jobs.py            # all companies in ats-map.json
     python3 fetch_jobs.py stripe ramp   # only these slugs
"""
import hashlib
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
DATA = os.path.join(ROOT, "data")
RESULTS = os.path.join(ROOT, "results")
SIMPLIFY_URL = ("https://raw.githubusercontent.com/SimplifyJobs/"
                "New-Grad-Positions/dev/.github/scripts/listings.json")
SIMPLIFY_REPO = "https://github.com/SimplifyJobs/New-Grad-Positions"
TIMEOUT = 20
MIN_POSTED = "2026-05-01"   # 只要 posted_date 在此日(含)之後的職缺

US_STATES = {"al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il",
    "in","ia","ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv",
    "nh","nj","nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn","tx",
    "ut","vt","va","wa","wv","wi","wy","dc"}

SWE_POS = ["software engineer", "software developer", "swe", "sde",
    "software development engineer", "full stack", "full-stack", "backend",
    "back end", "back-end", "frontend", "front end", "front-end",
    "software", "programmer", "web developer", "mobile engineer"]
SWE_NEG = ["sales engineer", "hardware engineer", "mechanical", "electrical",
    "firmware", "validation engineer", "manufacturing", "field engineer",
    "solutions engineer", "support engineer", "customer engineer",
    "systems administrator", "test engineer", "quality engineer"]

NG_POS = ["new grad", "new graduate", "new college grad", "college grad",
    "university grad", "university graduate", "early career", "entry level",
    "entry-level", "campus", "graduate", "early professional", "early talent",
    "2026", "associate software"]
NG_NEG = ["intern", "internship", "senior", "staff", "principal", " lead",
    "manager", "director", " sr", "sr.", "ii", "iii", " iv", " 2 ", " 3 ",
    "experienced", "mid-level", "mid level"]


# ---------- helpers ----------
def slugify(name):
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", name.lower()))


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def get_json(url, method="GET", data=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", "Mozilla/5.0 (job-board-fetcher)")
    if data is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(data).encode()
    try:
        with urllib.request.urlopen(req, data=data, timeout=TIMEOUT) as r:
            if r.status != 200:
                return None
            return json.loads(r.read())
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError,
            TimeoutError, ConnectionError, OSError):
        return None


def is_swe(title):
    t = (title or "").lower()
    if any(n in t for n in SWE_NEG) and "software" not in t:
        return False
    return any(p in t for p in SWE_POS)


def level_excluded(title):
    """Reject senior/intern/etc. — used to clean even the trusted Simplify feed."""
    t = " " + (title or "").lower() + " "
    return any(x in t for x in [" senior", " staff", " principal", " lead ",
        "intern", " manager", " director", " sr ", "sr.", " vp ", " fellow",
        " ii ", " iii "])


def degree_ok(degrees, title=""):
    """資格須為 Bachelor's 或 Master's。
    - 標題含 PhD -> 排除
    - 有標 degrees -> 必須含 bachelor/master（踢掉 PhD-only / Associate-only…）
    - 沒標 degrees（含 B 層 ATS 拿不到學歷）-> 視為未知，保留"""
    if "phd" in (title or "").lower():
        return False
    if degrees:
        return any("bachelor" in d.lower() or "master" in d.lower() for d in degrees)
    return True


HIGH_TIERS = {"Tier 1", "Tier 1.5", "Tier 2"}


def date_ok(posted, high_priority=False):
    """posted_date 須 >= MIN_POSTED。
    無日期：高優先 tier（1/1.5/2）仍保留，其餘排除。"""
    if not posted:
        return high_priority
    return posted >= MIN_POSTED


def is_new_grad(title):
    t = " " + (title or "").lower() + " "
    if any(n in t for n in NG_NEG):
        return False
    if any(p in t for p in NG_POS):
        return True
    # bare "Software Engineer I" / "Engineer 1"
    if re.search(r"engineer\s*(i|1)\b", t):
        return True
    return False


FOREIGN = re.compile(
    r"canada|united kingdom|u\.k|\bengland\b|\bireland\b|dublin|\bindia\b|"
    r"bangalore|bengaluru|hyderabad|singapore|australia|sydney|melbourne|"
    r"germany|berlin|munich|france|\bparis\b|netherlands|amsterdam|\bspain\b|"
    r"brazil|são paulo|\bmexico\b|\bjapan\b|tokyo|\bchina\b|shanghai|"
    r"beijing|\bkorea\b|seoul|toronto|vancouver|montreal|ottawa|calgary|"
    r"edmonton|winnipeg|waterloo|victoria|mississauga|israel|tel aviv|"
    r"\bpoland\b|romania|portugal|lisbon|zurich|\bswitzerland\b|"
    r",\s*(bc|on|ab|qc|mb|sk|ns|nb|nl|pe)\b")


def loc_is_us(s):
    t = (s or "").lower()
    if not t:
        return False
    if FOREIGN.search(t):           # foreign location -> not US (even if a stray
        return False               # US-looking token appears, e.g. "Winnipeg, MN")
    if any(k in t for k in ["united states", "usa", "u.s", " us", "us ", ", us"]):
        return True
    # ", CA" / ", NY" state suffix
    for m in re.findall(r",\s*([a-z]{2})\b", t):
        if m in US_STATES:
            return True
    if "remote" in t and not re.search(r"(canada|india|uk|ireland|europe|emea|"
            r"apac|london|berlin|toronto|singapore|australia|germany|france|"
            r"netherlands|spain|brazil|mexico|japan|china|korea)", t):
        return True
    return False


def any_us(locations):
    return any(loc_is_us(x) for x in locations) if locations else False


def to_date(v):
    """Accept ISO string or epoch (s or ms) -> YYYY-MM-DD or None."""
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (int, float)):
            ts = v / 1000 if v > 1e11 else v
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        s = str(v).replace("Z", "+00:00")
        return datetime.fromisoformat(s).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v))
        return m.group(1) if m else None


def job(slug, jid, title, locations, url, posted, board,
        etype="Full time", quals=None, salary=None, spons=None, fetched=None):
    return {"job_id": f"{slug}-{jid}", "title": title,
            "locations": locations or [], "apply_url": url,
            "posted_date": posted, "employment_type": etype,
            "qualifications": quals, "salary_range": salary,
            "sponsorship_note": spons, "job_board": board,
            "fetched_at": fetched, "applied": False, "screened": False}


# ---------- per-ATS parsers (return raw jobs; filtering done by caller) ----------
def from_greenhouse(slug, token, fetched):
    d = get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false")
    ok = d is not None
    out = []
    for j in (d or {}).get("jobs", []):
        loc = (j.get("location") or {}).get("name")
        out.append(job(slug, f"gh-{j.get('id')}", j.get("title"),
            [loc] if loc else [], j.get("absolute_url"),
            to_date(j.get("updated_at") or j.get("first_published")),
            "Greenhouse", fetched=fetched))
    src = f"https://boards.greenhouse.io/{token}"
    return out, src, ok


def from_lever(slug, token, fetched):
    d = get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    ok = d is not None
    out = []
    for j in (d or []):
        cats = j.get("categories") or {}
        loc = cats.get("location")
        locs = [loc] if loc else []
        if cats.get("allLocations"):
            locs = cats["allLocations"]
        out.append(job(slug, f"lever-{j.get('id')}", j.get("text"), locs,
            j.get("hostedUrl"), to_date(j.get("createdAt")),
            "Lever", etype=cats.get("commitment") or "Full time",
            fetched=fetched))
    return out, f"https://jobs.lever.co/{token}", ok


def from_ashby(slug, token, fetched):
    d = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    ok = d is not None
    out = []
    for j in (d or {}).get("jobs", []):
        locs = []
        if j.get("location"):
            locs.append(j["location"])
        for sl in j.get("secondaryLocations") or []:
            if isinstance(sl, dict) and sl.get("location"):
                locs.append(sl["location"])
        out.append(job(slug, f"ashby-{j.get('id')}", j.get("title"), locs,
            j.get("jobUrl") or j.get("applyUrl"),
            to_date(j.get("publishedAt") or j.get("updatedAt")),
            "Ashby", etype=j.get("employmentType") or "Full time",
            fetched=fetched))
    return out, f"https://jobs.ashbyhq.com/{token}", ok


def from_smartrecruiters(slug, token, fetched):
    out = []
    offset = 0
    ok = False
    while offset < 200:
        d = get_json("https://api.smartrecruiters.com/v1/companies/"
                     f"{token}/postings?limit=100&offset={offset}")
        if d is None:                 # network/HTTP failure -> signal, don't clobber
            break
        ok = True
        items = d.get("content", [])
        if not items:
            break
        for j in items:
            loc = j.get("location") or {}
            parts = [loc.get("city"), loc.get("region"), loc.get("country")]
            locstr = ", ".join(p for p in parts if p)
            if loc.get("remote"):
                locstr = (locstr + " (Remote)").strip()
            jid = j.get("id")
            url = f"https://jobs.smartrecruiters.com/{token}/{jid}"
            out.append(job(slug, f"sr-{jid}", j.get("name"),
                [locstr] if locstr else [], url,
                to_date(j.get("releasedDate") or j.get("createdOn")),
                "SmartRecruiters", fetched=fetched))
        if len(items) < 100:
            break
        offset += 100
    return out, f"https://jobs.smartrecruiters.com/{token}", ok


ATS = {"greenhouse": from_greenhouse, "lever": from_lever,
       "ashby": from_ashby, "smartrecruiters": from_smartrecruiters}


# ---------- Simplify (A layer) ----------
def load_simplify():
    """Return (index, ok). ok=False means the feed couldn't be reached — callers
    must NOT treat that as 'no jobs' (it would wipe good data)."""
    d = get_json(SIMPLIFY_URL)
    if d is None:
        return {}, False
    idx = {}
    for j in d:
        if not j.get("active") or j.get("is_visible") is False:
            continue
        idx.setdefault(norm(j.get("company_name")), []).append(j)
    return idx, True


def from_simplify(slug, name, idx, fetched, high=False):
    keys = {norm(name)}
    for part in re.split(r"[/&]", name):       # "TikTok / ByteDance" -> both
        keys.add(norm(part))
    out = []
    seen = set()
    for k in keys:
        if not k:
            continue
        for j in idx.get(k, []):
            jid = j.get("id")
            if jid in seen:
                continue
            seen.add(jid)
            title = j.get("title")
            degrees = j.get("degrees") or []
            posted = to_date(j.get("date_posted"))
            # filters: SWE + US + new-grad level + degree(Bachelor/Master) + date
            if not (is_swe(title) and any_us(j.get("locations") or [])
                    and not level_excluded(title)
                    and degree_ok(degrees, title) and date_ok(posted, high)):
                continue
            quals = ", ".join(degrees) or None
            out.append(job(slug, f"smpl-{jid}", title,
                j.get("locations") or [], j.get("url"),
                posted, "Simplify",
                quals=quals, spons=j.get("sponsorship"), fetched=fetched))
    return out


# ---------- GitHub markdown lists (A layer, like Simplify) ----------
SPEEDY_URL = ("https://raw.githubusercontent.com/speedyapply/"
              "2026-SWE-College-Jobs/main/NEW_GRAD_USA.md")
SPEEDY_REPO = "https://github.com/speedyapply/2026-SWE-College-Jobs"


def get_text(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (job-board-fetcher)")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            if r.status != 200:
                return None
            return r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, urllib.error.HTTPError,
            TimeoutError, ConnectionError, OSError):
        return None


def clean_level_excluded(title):
    """level_excluded on a punctuation-normalized title, so 'Engineer II,' or
    'Engineer III)' still match the token checks."""
    t = re.sub(r"[^a-z0-9]+", " ", (title or "").lower())
    return level_excluded(f" {t} ")


def age_to_date(s, today):
    """'6d' / '2w' / '3mo' / '5h' -> YYYY-MM-DD."""
    m = re.match(r"(\d+)\s*(mo|[hdw])", s.strip().lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    days = {"h": 0, "d": n, "w": 7 * n, "mo": 30 * n}[unit]
    from datetime import timedelta
    return (today - timedelta(days=days)).strftime("%Y-%m-%d")


def board_from_url(url):
    u = (url or "").lower()
    for pat, name in [("greenhouse.io", "Greenhouse"), ("lever.co", "Lever"),
                      ("ashbyhq.com", "Ashby"),
                      ("smartrecruiters.com", "SmartRecruiters"),
                      ("icims.com", "iCIMS")]:
        if pat in u:
            return name
    return "Company careers"


def load_speedyapply():
    """speedyapply/2026-SWE-College-Jobs NEW_GRAD_USA.md table -> index."""
    md = get_text(SPEEDY_URL)
    if md is None:
        return {}, False
    today = datetime.now()
    idx = {}
    for line in md.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # two layouts: 6 cols (Company|Position|Location|Salary|Posting|Age)
        # and 5 cols (Company|Position|Location|Posting|Age — the big "Other" table)
        if len(cells) < 5 or cells[0].startswith("---") or cells[0] == "Company":
            continue
        salary = cells[3] if len(cells) >= 6 else None
        link_c = cells[4] if len(cells) >= 6 else cells[3]
        age_c = cells[5] if len(cells) >= 6 else cells[4]
        cm = re.search(r"<strong>([^<]+)</strong>", cells[0])
        am = re.search(r'href="([^"]+)"', link_c)
        if not (cm and am):
            continue
        company, url = cm.group(1).strip(), am.group(1)
        if "myworkdayjobs.com" in url.lower():
            continue                       # skip Workday-routed postings
        hid = hashlib.md5(url.encode()).hexdigest()[:10]
        idx.setdefault(norm(company), []).append({
            "id": hid, "company": company,
            "title": re.sub(r"<[^>]+>", "", cells[1]).strip(),
            "url": url,
            "locations": [cells[2]] if cells[2] else [],
            "posted_date": age_to_date(age_c, today),
            "salary": salary or None,
            "board": board_from_url(url)})
    return idx, True


def from_listmd(slug, name, idx, fetched, high, prefix):
    """Filter+wrap raw entries from a markdown-list index (speedyapply).
    Curated new-grad lists, but they leak SWE II/senior rows -> level guard."""
    keys = {norm(name)}
    for part in re.split(r"[/&]", name):
        keys.add(norm(part))
    out, seen = [], set()
    for k in keys:
        if not k:
            continue
        for r in idx.get(k, []):
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            title = r["title"]
            if not (is_swe(title) and any_us(r["locations"])
                    and not clean_level_excluded(title)
                    and degree_ok(None, title)
                    and date_ok(r["posted_date"], high)):
                continue
            out.append(job(slug, f"{prefix}-{r['id']}", title, r["locations"],
                r["url"], r["posted_date"], r["board"],
                salary=r["salary"], fetched=fetched))
    return out


def dup_keys(j):
    """Keys for cross-source dedup: normalized URL, posting-id tokens in the URL,
    and (title+location) — the last one only kills dups ACROSS different boards."""
    keys = set()
    u = re.sub(r"[?#].*$", "", (j["apply_url"] or "").lower()).rstrip("/")
    u = re.sub(r"/apply$", "", u)
    if u:
        keys.add("u:" + u)
        for m in re.findall(r"\d{6,}", u):
            keys.add("n:" + m)
        for m in re.findall(r"jr\d{6,}", u):
            keys.add("n:" + m)
    return keys


def title_key(j):
    return "t:" + norm(j["title"]) + "|" + norm((j["locations"] or [""])[0])


# ---------- merge + write ----------
def load_existing(path):
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("jobs", [])
    except (ValueError, OSError):
        return []


def write_company(name, slug, jobs, source, fetched):
    path = os.path.join(RESULTS, f"{slug}.json")
    existing = load_existing(path)
    applied = {j["job_id"] for j in existing if j.get("applied")}
    screened = {j["job_id"] for j in existing if j.get("screened")}
    seen_at = {j["job_id"]: j.get("fetched_at") for j in existing}

    # Carry over browser/manually-added jobs (job_id 含 "-manual-") so a fresh
    # A+B fetch doesn't wipe what Cowork found in LinkedIn / company sites.
    fresh_urls = {(j.get("apply_url") or "").rstrip("/").lower() for j in jobs}
    for m in existing:
        if "-manual-" in m.get("job_id", "") and \
           (m.get("apply_url") or "").rstrip("/").lower() not in fresh_urls:
            jobs.append(m)

    for j in jobs:
        if j["job_id"] in applied:
            j["applied"] = True
        if j["job_id"] in screened:      # keep resume-screened state across re-fetch
            j["screened"] = True
        j.setdefault("screened", False)
        # keep the original per-job fetched_at for postings we've seen before;
        # only brand-new ones get this run's timestamp (so it means "first seen"
        # and doesn't churn every refresh).
        if seen_at.get(j["job_id"]):
            j["fetched_at"] = seen_at[j["job_id"]]
    doc = {"company": name, "slug": slug, "fetched_at": fetched,
           "source": source, "job_count": len(jobs), "jobs": jobs}
    os.makedirs(RESULTS, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def main():
    only = set(sys.argv[1:])
    with open(os.path.join(DATA, "ats-map.json"), encoding="utf-8") as f:
        amap = json.load(f)["companies"]

    try:
        with open(os.path.join(DATA, "tiers.json"), encoding="utf-8") as f:
            tmap = json.load(f)["tiers"]
    except (ValueError, OSError):
        tmap = {}

    print("downloading Simplify listings…", file=sys.stderr)
    simplify, simplify_ok = load_simplify()
    if not simplify_ok:
        # No outbound network to the job sources (e.g. a firewalled sandbox).
        # Abort WITHOUT writing — overwriting with empty results would wipe the
        # existing board. Run the schedule on a host with network instead.
        print("ERROR: cannot reach the Simplify feed (network/firewall?). "
              "Aborting — no files written, existing results/ preserved.",
              file=sys.stderr)
        sys.exit(2)
    print("downloading speedyapply list…", file=sys.stderr)
    speedy, sa_ok = load_speedyapply()
    if not sa_ok:
        print("  warn: speedyapply list unreachable — continuing without it",
              file=sys.stderr)

    fetched = datetime.now().astimezone().isoformat(timespec="seconds")

    total_jobs = 0
    written = 0
    for slug, info in amap.items():
        if only and slug not in only:
            continue
        name, system, token = info["name"], info["system"], info.get("token")
        high = tmap.get(slug) in HIGH_TIERS   # Tier 1/1.5/2 -> 缺日期也收

        jobs, source = [], SIMPLIFY_REPO
        if system in ATS and token:
            jobs, source, b_ok = ATS[system](slug, token, fetched)
            if not b_ok:
                # ATS unreachable this run -> keep the existing file, don't clobber
                print(f"  skip {name}: {system} unreachable (kept existing)",
                      file=sys.stderr)
                continue
            # B-layer: SWE + new-grad + US + degree(title-based) + date.
            # (ATS list APIs lack a degree field -> degree_ok treats it as unknown
            #  and only filters out PhD-titled roles.)
            jobs = [j for j in jobs if is_swe(j["title"])
                    and is_new_grad(j["title"]) and any_us(j["locations"])
                    and degree_ok(None, j["title"]) and date_ok(j["posted_date"], high)]

        # A-layer (every company): each loader already applies all filters.
        # Priority: ATS (canonical) > Simplify (sponsorship info) >
        # speedyapply (real ATS url + salary).
        smpl = from_simplify(slug, name, simplify, fetched, high)
        sa = from_listmd(slug, name, speedy, fetched, high, "sa")

        # cross-source dedup: URL/posting-id keys always; title+location key only
        # across different boards (same-board same-title roles are distinct posts)
        merged, seen, tboard = [], set(), {}
        for j in jobs + smpl + sa:
            ks = dup_keys(j)
            tk = title_key(j)
            if ks & seen:
                continue
            if tk in tboard and tboard[tk] != j["job_board"]:
                continue
            seen |= ks
            tboard.setdefault(tk, j["job_board"])
            merged.append(j)

        # write a file if we genuinely queried a B source, or found anything
        if system in ATS or merged:
            write_company(name, slug, merged, source, fetched)
            written += 1
            total_jobs += len(merged)
            if merged:
                print(f"  {name:<28} {len(merged):>3} jobs ({system})", file=sys.stderr)

    print(f"\nDONE: wrote {written} files, {total_jobs} jobs total", file=sys.stderr)


if __name__ == "__main__":
    main()
