# GradPilot — New-Grad SWE Job Board

A personal job-hunt tool for the new-grad cycle. A company **tier list** doubles
as a **job board**: automated fetchers pull new-grad SWE openings per company into
`results/{slug}.json`, a single-file HTML page lets you browse them (per company or
all at once), mark what you've applied to, and an AI skill simulates the
**automated resume-screening gate** for each job against two resume profiles.

## Quick start (after cloning)

Requires only Python 3 (stdlib — nothing to install).

```bash
git clone https://github.com/kypkk/GradPilot.git gradpilot && cd gradpilot

# 1) One-time setup
python3 scripts/discover_ats.py            # probe every company -> data/ats-map.json
                                           #   (gitignored, takes a few minutes)
cp resume/example.tex resume/backend-infra.tex   # then replace with your real resume either .tex or .pdf

# 2) Fetch jobs (A + B layers)
bash scripts/run_ab.sh                     # -> results/{slug}.json, log: refresh.log

# 3) Browse the board
python3 server.py                          # http://localhost:8000/swe-tier-list.html
```

> Use `server.py`, not `python3 -m http.server` — the server also persists the
> "applied" toggle back into the JSON files.

The company tier list lives in the inline `data` object of `swe-tier-list.html`.
After editing it, re-sync with `python3 scripts/make_lists.py` (and re-run
`discover_ats.py` so new companies get fetched).

Steps 1–3 give you the script-only board. The AI parts — the LinkedIn/in-house
browser dive and resume screening — run as the two skills below.

## The two Claude skills

### `newgrad-job-refresh` (.claude/skills/newgrad-job-refresh/)

The browser half of the refresh. Using a logged-in Chrome (Claude-in-Chrome), it
deep-dives LinkedIn and the Tier 1/1.5/2 + in-house ("other") companies' own career
sites — the places the script APIs can't reach — applies the same filters as the
fetcher, dedups against what's already in `results/{slug}.json` by apply URL, and
merges **only genuinely new roles** via `scripts/add_jobs.py` (stable `-manual-` ids
that survive future fetch overwrites). It never runs the A+B scripts itself.

### `resume-screen` (.claude/skills/resume-screen/)

Simulates the automated screening gate for a job. For each job × each resume profile
(`backend-infra`, `ai-mlops`), it fetches the full job description from the apply
URL, applies **knockout filters first** (work authorization / sponsorship, US
location, graduation timing, degree, experience), then scores the content match
0–100 with missing keywords and honest fix suggestions. Results go to
`screenings/screenings.json` (keyed by `job_id`, decoupled from the fetch pipeline)
via `scripts/save_screening.py`, which also flips the job's `screened` flag in
`results/`. The board overlays per-profile badges (pass / borderline / knockout) on
every screened job and can sort all jobs by best screening score.

## Using the skills (Claude Code / Cowork / other harnesses)

Both skills are standard [Agent Skills](https://code.claude.com/docs/en/skills)
(`SKILL.md` folders) under `.claude/skills/`, scoped to this project. The only hard
requirement: **the agent must run with this repo as its working directory**, with
bash + python3 available. The refresh skill additionally needs a controllable Chrome
that's logged into LinkedIn; resume-screen needs your resume profiles in `resume/`
(`.tex` or `.pdf`) and a way to open each job's apply URL (browser tool or web fetch).

**Claude Code (CLI):**

```bash
cd gradpilot && claude
```

Project skills are discovered automatically. Just ask in natural language:

- `refresh the job board` / `check LinkedIn for new grad roles` → `newgrad-job-refresh`
- `screen my resume against the stripe jobs` / `run resume screening for everything
not screened yet` → `resume-screen`

**Claude Cowork (desktop):** open this repo folder as the session's project folder —
the skills are picked up the same way. Install the Claude-in-Chrome extension and keep
a Chrome window logged into LinkedIn for the browser dive. For unattended runs, create
two scheduled tasks whose prompts ask for the skill by name, e.g.:

- twice daily: _"In <repo path>, use the newgrad-job-refresh skill to do the browser
  deep-dive only (don't run fetch_jobs.py / prune_dead.py — schedule
  `bash scripts/run_ab.sh` separately, e.g. via cron/launchd). Add only roles whose
  apply_url isn't already in results/{slug}.json, then report what's new."_
- offset by 30 min: _"In <repo path>, use the resume-screen skill to screen every job
  whose `screened` field is false in results/, against both resume profiles, and
  report the verdict breakdown."_

**Other harnesses (OpenClaw, or anything that supports Agent Skills):** copy or
symlink the two folders from `.claude/skills/` into your harness's skills directory
(e.g. `~/.openclaw/skills/`), then run the agent with this repo as cwd and ask the
same way. The skills are self-contained instructions — no Claude-specific tooling
beyond a shell, a browser tool for the dive, and the scripts in this repo.

## Changing the start-fetch date

Jobs posted before this date are dropped (except dateless Tier 1/1.5/2 roles).
It's set in **two places — keep them equal**:

1. `scripts/fetch_jobs.py` — the `MIN_POSTED` constant at the top:
   ```python
   MIN_POSTED = "YYYY-MM-DD"   # e.g. the start of your recruiting season
   ```
2. `.claude/skills/newgrad-job-refresh/SKILL.md` — the same date in the browser
   dive's filter step (step 3).

## Resume profiles

Put your two profiles in `resume/` as `backend-infra` and `ai-mlops`, each as
`.tex` or `.pdf` (when both exist the skill reads the `.tex`). `resume/example.tex`
is a starting skeleton. Real resumes are gitignored.

## Scheduling

- **A+B scripts**: cron/launchd whatever you like — e.g. macOS launchd calling
  `bash scripts/run_ab.sh` twice a day. Needs outbound network; if the network is
  unreachable the fetcher aborts without writing (it never wipes the board).
- **Browser dive + resume screening**: schedule the two skills (e.g. Claude Cowork
  scheduled tasks) in an environment with a logged-in Chrome.
