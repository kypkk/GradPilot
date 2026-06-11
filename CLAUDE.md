# 2026Fall — New Grad SWE Job Board

A personal job-hunt tool. A company **tier list** doubles as a **job board**: a
fetcher pulls new-grad SWE openings per company into `results/{slug}.json`, and the
HTML page lets you browse them per-company or all-at-once and mark which you've
applied to.

Owner is an international new grad — graduates **2026-12-08**, targeting an offer
before **2027-02-28**. Sponsorship visibility matters (red names = sponsorship
uncertain).

## Files

- `swe-tier-list.html` — the whole UI (single file, no framework, no build step).
  An inline `data` object holds ~337 companies across 5 tiers. Each entry:
  `{n: name, r?: sponsorship-uncertain (red), m?: 'up'|'down' (moved tier), a?: 1
  (newly added)}`.
- `server.py` — local server (Python stdlib only). Serves the folder + persists the
  `applied` flag back into JSON. **Use this, not `python3 -m http.server`** (that
  can't write).
- `results/{slug}.json` — one file per company, written by the fetcher.
- `docs/superpowers/specs/2026-06-03-tier-list-job-board-design.md` — full design spec.

**Layout** (the app — `server.py` + `swe-tier-list.html` — and the data dirs stay at
root because the page fetches `results/` and `screenings/` relatively):
```
swe-tier-list.html  server.py        ← the app (run from root)
scripts/   fetch_jobs · discover_ats · add_jobs · prune_dead · make_lists ·
           save_screening · run_ab.sh    (every .py finds the project root via __file__)
data/      companies.txt · tiers.json · ats-map.json · cowork-companies.json
results/   per-company job JSON          resume/   two resume profiles
screenings/ screenings.json + reports/   docs/  .claude/skills/
```

## Run

```bash
python3 server.py            # port 8000 (or: python3 server.py 8080)
# open http://localhost:8000/swe-tier-list.html
```

## UI

- **分級表** tab: the 5-tier grid. Companies with fetched data show a job count + green
  dot; un-fetched ones are dimmed but still clickable. Click → company detail view.
- **全部職缺** tab: every fetched job across all companies in one list, **most recent on
  top**. Sort dropdown: 最近抓取 (`fetched_at`) / 最近發布 (`posted_date`); null dates sink
  to the bottom. Each row links back to its company.
- Detail view: per-job cards with an **Applied** toggle that writes back to the file.

## Data contract (the fetcher MUST follow this)

`slugify(name)`: lowercase → non-alphanumeric runs become a single `-` → trim `-`.
Same function is embedded in the HTML. Examples: `TikTok / ByteDance` →
`tiktok-bytedance`, `McKinsey & Company` → `mckinsey-company`.

File shape — `results/{slug}.json`:

```json
{
  "company": "Stripe", "slug": "stripe",
  "fetched_at": "2026-06-03T11:25:28+08:00",   // ISO-8601 + timezone
  "source": "https://...search-url",            // the search/careers URL
  "job_count": 1,
  "jobs": [{
    "job_id": "stripe-7176977",                 // STABLE across re-fetches
    "title": "...", "locations": ["..."],
    "apply_url": "https://...",
    "posted_date": "2026-05-28",                 // YYYY-MM-DD or null
    "employment_type": "Full time",
    "qualifications": "...",
    "salary_range": null,
    "sponsorship_note": null,
    "job_board": "Greenhouse",                   // platform behind apply_url
    "fetched_at": "2026-06-03T11:25:28+08:00",
    "applied": false,
    "screened": false                            // resume-screened yet? (set by resume-screen)
  }]
}
```

Rules:
- **Unknown values → `null`** (or `[]` for `locations`). Never omit keys.
- **`applied` and `screened`** are preserved across re-fetches (carried over by
  `job_id`, like applied). New jobs start `screened: false`; `scripts/save_screening.py`
  flips it to `true` when a job is resume-screened. The resume-screen task screens jobs
  where `screened == false`.
- **`job_id` must be stable** (real posting ID, else hash of company+title+apply_url) —
  the `applied` flag is keyed to it.
- **Merge on re-fetch:** read the existing file first and carry over `applied: true`
  for any `job_id` still present, so re-fetches don't reset what was marked.
- Always populate per-job `fetched_at` (the UI falls back to file-level if missing,
  but don't rely on it).
- **Company matching is case-insensitive** — `Amazon.json` / `amazon.json` both work,
  but prefer writing the lowercase slug filename.

## Fetching jobs — the pipeline

Three source layers (full reference: `docs/job-boards.md`):

| File | Role |
|---|---|
| `scripts/make_lists.py` | regenerates `data/companies.txt` + `data/tiers.json` from the HTML (run after editing the company list). |
| `data/companies.txt` | flat list of every company name in the HTML (one per line). |
| `data/tiers.json` | `{slug: "Tier 1"|…}` — lets the fetcher treat Tier 1/1.5/2 as high-priority. |
| `scripts/discover_ats.py` | probes each company against Greenhouse/Lever/Ashby/SmartRecruiters → writes `data/ats-map.json` (company → ATS + token; unmatched = `"other"`). Re-run occasionally. |
| `data/ats-map.json` | the discovered map. ~103 on the 4 ATS; ~202 `"other"`. |
| `scripts/fetch_jobs.py` | **the A+B fetcher.** `python3 scripts/fetch_jobs.py` (all) or `… stripe ramp` (subset). |
| `scripts/add_jobs.py` | merges browser/manually-found jobs into `results/{slug}.json` (stable `-manual-` id, dedup, preserves `applied`). Used by the refresh skill's LinkedIn dive. |
| `scripts/prune_dead.py` | removes definitively-dead (404/410) postings; keeps anti-bot/timeout and `applied` ones. |
| `data/cowork-companies.json` | the `"other"` companies (B.5/C) for Claude Cowork to fetch manually. |

**Tier-aware date rule:** `fetch_jobs.py` keeps Tier 1/1.5/2 roles even when the post
date is unknown; Tier 3/4 require a date ≥ `MIN_POSTED`. `-manual-` jobs added via
`add_jobs.py` survive future `fetch_jobs.py` runs (they're carried over on overwrite).

## Scheduled refresh — split into two halves

The refresh is split by which network each half has:

**A + B → run the scripts (where bash has network).** `bash scripts/run_ab.sh` runs
`fetch_jobs.py` (Simplify + 4 ATS) then `prune_dead.py`, logging to `refresh.log`.
Pure scripts, no AI/browser. **The local launchd agent that ran this twice daily was
removed (2026-06-05)** — run `bash scripts/run_ab.sh` manually, or re-add a
launchd/cron schedule when you want it automated again.

**B.5 + C → Claude Cowork, via the `newgrad-job-refresh` skill, in the logged-in
Chrome.** Deep-dives LinkedIn + the Tier 1/1.5/2 + in-house/"other" sites the ATS
fetch can't reach, and **adds only new roles** (dedup vs the existing file) with
`add_jobs.py`. Schedule it (e.g. the `schedule` skill / scheduled-tasks) in an
environment where a logged-in Chrome is reachable.

**Network safety:** `fetch_jobs.py` aborts (exit 2, writes nothing) if it can't reach
the Simplify feed, and skips any single company whose ATS is unreachable — so a
no-network run can't wipe the existing board. Early-season (June) results are thin —
that's expected.

**`fetch_jobs.py` does:**
- **A layer:** downloads three community new-grad lists and matches by company name —
  Simplify `listings.json` (has `sponsorship`), **jobright-ai/2026-Software-Engineer-
  New-Grad** (README table; jobright.ai redirect links), and **speedyapply/2026-SWE-
  College-Jobs** `NEW_GRAD_USA.md` (real ATS links + salary). Cross-source dedup is by
  normalized URL + posting-id tokens in the URL + (title+location) across different
  boards. The markdown lists leak SWE II/senior rows → `clean_level_excluded` guard.
- **B layer:** calls each mapped company's ATS API (Greenhouse/Lever/Ashby/
  SmartRecruiters).
- Filters to **SWE + new-grad + US + degree(Bachelor's/Master's) + posted ≥
  `MIN_POSTED`** (`is_swe` / `is_new_grad` / `loc_is_us`+`FOREIGN` / `degree_ok` /
  `date_ok`). Degree: Simplify has a `degrees` field (drop PhD-only/Associate-only,
  keep untagged); ATS list APIs lack it so only PhD-titled roles are dropped. Date
  cutoff `MIN_POSTED` (top of `fetch_jobs.py`) is currently `2026-05-01`.
- Dedups by `apply_url`, **merges existing `applied`**, writes `results/{slug}.json`.
- Run all: `python3 scripts/fetch_jobs.py` · subset: `python3 scripts/fetch_jobs.py stripe ramp`.

**Cowork's job (B.5/C, every 6h alongside the script):** work through
`cowork-companies.json` — the in-house/Workday/iCIMS/JS-rendered sites the script
can't hit — using a headless browser, writing the same `results/{slug}.json` shape.

- Postings rotate/expire fast — re-verify each run. Early season (June) most Fall
  new-grad roles aren't posted yet; expect thin results (first run: ~137 jobs).

## Resume screening (the `resume-screen` skill)

Simulates the **automated screening gate** for a job against the owner's **two resume
profiles** (`backend-infra`, `ai-mlops`), B fidelity = content match **+ knockout
filters** (work-auth/sponsorship, US location, grad timing, degree, experience).
Separate from the job-fetch pipeline.

| File | Role |
|---|---|
| `resume/{backend-infra,ai-mlops}.tex` (+ `.pdf`) | the two resume profiles (skill reads `.tex`; `.pdf` for later parse checks). See `resume/README.md`. |
| `.claude/skills/resume-screen/SKILL.md` | the Cowork skill: per job × profile → `badge` (pass/borderline/knockout) + `score` + missing/fixes; fetches the full JD from `apply_url`. |
| `scripts/save_screening.py` | merges one job's result into `screenings/screenings.json` (keyed by `job_id`; never hand-edit the JSON). |
| `screenings/screenings.json` | decoupled store, keyed by `job_id` (joins to `results/`); **never touched by `fetch_jobs.py`**. |
| `screenings/reports/{job_id}-{profile}.md` | human-readable per-screen report. |

The board (`swe-tier-list.html`) loads `screenings/screenings.json` and overlays two
badges (BE / ML) on each job in the all-jobs rows and detail cards — green=pass,
amber=borderline, red=knockout, with score + tooltip; nothing shown for unscreened
jobs. Badge thresholds: pass ≥75 & no knockout, borderline 50–74, knockout = any
knockout or <50. Later (phase D): a Python+Claude-API batch scorer + sort 全部職缺 by
score. Full design: `docs/superpowers/specs/2026-06-05-resume-screen-design.md`.

## Conventions

- Keep `swe-tier-list.html` a single self-contained file. Match its existing vanilla-JS
  style (no frameworks, no bundler).
- UI copy is in Traditional Chinese; keep new strings consistent.
- Don't fabricate sample data in `results/` — stub URLs 404 and mislead. Use real
  fetches or temporary test files you delete after verifying.
