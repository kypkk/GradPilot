---
name: newgrad-job-refresh
description: >-
  Cowork's half of the 2026Fall new-grad job board refresh: deep-dive LinkedIn and
  the Tier 1/1.5/2 + in-house ("other") companies' own career sites in the logged-in
  Chrome, and add ONLY the new roles the automated A+B fetch can't reach. USE THIS
  whenever it's time to refresh the board — on the twice-daily schedule, or when the
  user says "refresh the job board", "check LinkedIn for new grad roles", "do the
  browser job dive", "fetch new jobs", "pull the latest openings", or "run the
  scheduled job task". The A+B layer (Greenhouse/Lever/Ashby/SmartRecruiters +
  Simplify) is handled automatically by a local launchd job — this skill is the
  browser-driven B.5/C part. Trigger it even if the user only implies a refresh.
---

# New-Grad Job Board Refresh — Cowork's browser part (B.5 + C)

## Split of responsibilities (important)

- **A + B scripts (run separately, where bash has network):** `bash scripts/run_ab.sh`
  calls `scripts/fetch_jobs.py` (Simplify + the 4 ATS) then `scripts/prune_dead.py`.
  Run manually or on a schedule the owner sets up. **You (Cowork) do NOT do this part**
  — and in a no-network sandbox `fetch_jobs.py` just aborts safely anyway.
- **You (Cowork), this skill — B.5 + C, via the logged-in Chrome:** deep-dive
  LinkedIn and the Tier 1/1.5/2 companies + the in-house/"other" sites the API fetch
  can't reach, and **add only the genuinely new roles** to `results/{slug}.json`.

Goal: an international new grad (graduates 2026-12-08, wants an offer before
2027-02-28) sees fresh, relevant roles the scripts miss. Relevant = **SWE · new-grad ·
US · Bachelor's/Master's**. For Tier 1/1.5/2, keep a role even if you can't find a
post date (they're worth tracking regardless).

## Preconditions

- A **Chrome logged into LinkedIn**, reachable via the Claude-in-Chrome tools. If it
  isn't available, there's nothing for this skill to do — say so and stop (the
  A+B scripts still keep the board current).
- Working directory is the project root `/Users/kangkang/kypkk/2026Fall`.
- Skim `CLAUDE.md` (data contract + filters) if unfamiliar — don't duplicate it here.

## The browser dive — step by step

### 1. Build the target list (Tier 1/1.5/2)
```bash
python3 -c "import json;t=json.load(open('data/tiers.json'))['tiers'];print('\n'.join(s for s,v in t.items() if v in ('Tier 1','Tier 1.5','Tier 2')))"
```
Work **Tier 1 → 1.5 → 2**. If you run low on time, stop and record where you stopped
(in the summary) so the next run resumes there — covering Tier 1 well beats covering
everything badly.

### 2. For each company, search in the logged-in Chrome
- **LinkedIn Jobs** and the **company's own careers site** for new-grad SWE roles in
  the US (terms: "new grad software engineer", "university graduate", "early career
  software"; filter location = United States, date = past week/month).
- The "other"/in-house giants (Google, Amazon, Apple, Meta, Microsoft…) are exactly
  where this matters — their sites aren't on the 4 ATS the script covers.

### 3. Filter (match the script's judgment so the two stay consistent)
Keep only: **SWE** role · **new-grad** level (drop intern/senior/staff/PhD-only) ·
**US** location · open to **Bachelor's or Master's** · **posted on/after 2026-05-01**
(the start-fetch date — keep this equal to `MIN_POSTED` at the top of
`scripts/fetch_jobs.py`). Tier 1/1.5/2: keep even if the post date is unknown.

### 4. Add ONLY new roles (dedup against what's already there)
Before adding, read the company's existing file and skip anything already present:
```bash
python3 -c "import json,sys;d=json.load(open('results/google.json'));print('\n'.join(j['apply_url'] for j in d['jobs']))" 2>/dev/null
```
Collect only roles whose **apply_url is not already in that file** (also eyeball the
title to avoid the same role at a different URL). Then merge — never hand-edit JSON:
```bash
python3 scripts/add_jobs.py new_jobs.json
```
`new_jobs.json` (one object or a list):
```json
{"company":"Google","slug":"google",
 "source":"https://www.linkedin.com/jobs/...",
 "jobs":[{"title":"Software Engineer, Early Career","locations":["Mountain View, CA"],
          "apply_url":"https://www.google.com/about/careers/applications/jobs/results/123",
          "posted_date":"2026-06-01","job_board":"LinkedIn",
          "sponsorship_note":null,"salary_range":null,"qualifications":null}]}
```
`add_jobs.py` gives a stable `…-manual-…` id, **dedups by apply_url** (so even if you
re-submit one, no duplicate appears), and preserves `applied`. These `-manual-` jobs
**survive the A+B fetch overwrites**, so a role you add stays until it dies.

### 5. (Optional, while you're there) fill careers URLs for Tier 1–2 "other" companies
```bash
python3 -c "import json;t=json.load(open('data/tiers.json'))['tiers'];c=json.load(open('data/cowork-companies.json'))['companies'];print('\n'.join(f\"{x['name']} ({x['slug']})\" for x in c if t.get(x['slug']) in ('Tier 1','Tier 1.5','Tier 2') and not x.get('careers_url'))) "
```
Open each, write its real `careers_url` / `system_guess` / `notes` back into
`data/cowork-companies.json`. Makes the next run faster.

### 6. Summarize
Tell the user what's **new this run** (company + title), and note any Tier 1–2
companies you didn't finish so the next run resumes there.

## Don't

- **Don't run `fetch_jobs.py` / `prune_dead.py`** — that's the A+B scripts' job.
  (In a no-network sandbox they abort/no-op anyway.)
- Never fabricate a posting or apply URL — only add roles you actually opened.
- Browse at human pace with the existing session; don't hammer LinkedIn.
- A thin run is fine — early season (June) most Fall roles aren't posted yet.

## Reference: the A+B scripts (you don't run these; they're the other half)

- `bash scripts/run_ab.sh` → `scripts/fetch_jobs.py` + `scripts/prune_dead.py`,
  logs to `refresh.log`. Run manually or on a schedule the owner sets up (there is no
  longer a launchd agent for it).
