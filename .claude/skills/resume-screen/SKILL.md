---
name: resume-screen
description: >-
  Simulate the automated resume-screening gate for the 2026Fall job board:
  for a given job (or several), judge whether the owner's resume would clear the
  machine screen, against BOTH resume profiles (backend-infra and ai-mlops), with a
  score + verdict badge each, and write the result to screenings/screenings.json
  (joined to results/ by job_id). USE THIS when the user says things like "screen my
  resume", "would I pass the ATS for this job", "check my resume against this role",
  "run resume screening", "score my resume vs these jobs", or "would this get
  filtered out". Separate from newgrad-job-refresh (which only fetches jobs). Trigger
  whenever the user wants to know if a posting would auto-reject them.
---

# Resume Screening Simulator (B fidelity: knockouts + content match)

Simulates the **automated screening stage** — the keyword/requirements filter and
application-form knockouts that auto-reject a candidate *before a human reads the
resume*. Runs per job, against **both** resume profiles, and writes scores + verdict
badges that the board overlays on each job.

Owner is an **international new grad** — graduates **2026-12-08**, needs **visa
sponsorship**, no US citizenship/clearance. That makes work-authorization the single
biggest real knockout, so weight it heavily.

## Preconditions

- Working directory = project root `/Users/kangkang/kypkk/2026Fall`.
- Resume profiles present in `resume/`, as `.tex` or `.pdf` (read `.tex` when both
  exist — it's cleaner to parse; otherwise read the `.pdf` directly):
  - `resume/backend-infra.tex` or `.pdf` — profile key **`backend-infra`** (Backend/Infra)
  - `resume/ai-mlops.tex` or `.pdf` — profile key **`ai-mlops`** (AI Eng / MLOps)
  If a profile has neither file, say so and screen only the one(s) present.

## Inputs per job

- The job from `results/{slug}.json` (has `title`, `apply_url`, `qualifications`,
  `sponsorship_note`, `locations`, `job_id`).
- **Fetch the full JD** from `apply_url` (the stored fields are thin — you need the
  real requirements). Use WebFetch or the browser.

## How to screen one job × one profile

Apply these in order. **Knockouts first** — a single hard fail makes the verdict
`knockout` regardless of content.

**1. Knockout filters (hard auto-reject → badge `knockout`)**
- **Work authorization / sponsorship:** JD says "US citizenship required", "must be a
  US person", "active clearance", "no sponsorship / will not sponsor" → knockout
  (owner needs sponsorship). This is the most important check.
- **Location:** role is non-US / on-site in a country the owner can't work in → knockout.
- **Graduation timing:** required start date or grad window the owner (Dec 2026) can't
  meet → knockout.
- **Degree:** requires a degree the owner lacks (e.g., PhD-required) → knockout.
- **Experience:** clearly wants senior/N+ years (not a new-grad role) → knockout.

**2. Content / keyword match (if no knockout) → score 0–100**
- Extract the JD's required + preferred skills, technologies, and qualifications.
- Compare against the resume profile's content. Weight **must-haves** heavily;
  preferred items lightly.
- `score` = how well the resume covers what an ATS/keyword filter would look for.
- Record `missing` (key required items absent from the resume) and `fixes` (concrete,
  honest resume edits — only things the owner could truthfully add/surface, never
  fabricated experience).

**3. Verdict badge**
- `pass` — score ≥ 75 and no knockout.
- `borderline` — score 50–74 and no knockout.
- `knockout` — any hard knockout, **or** score < 50.

## Output

For each screened job, write **one Markdown report per profile** to
`screenings/reports/{job_id}-{profile}.md` (verdict, score, knockouts, missing,
fixes, the JD requirements you extracted), then merge the structured result — never
hand-edit the JSON:

```bash
python3 scripts/save_screening.py entry.json
```
`entry.json`:
```json
{ "job_id":"amazon-smpl-bfa6…", "company":"Amazon",
  "title":"Software Development Engineer",
  "profiles":{
    "backend-infra":{"badge":"pass","score":82,"knockouts":[],
      "missing":["Kubernetes"],"fixes":["Surface your k8s coursework project"],
      "report":"screenings/reports/amazon-smpl-bfa6…-backend-infra.md"},
    "ai-mlops":{"badge":"knockout","score":40,
      "knockouts":["US citizenship required"],"missing":["PyTorch"],"fixes":[],
      "report":"screenings/reports/amazon-smpl-bfa6…-ai-mlops.md"}
  }}
```
`scripts/save_screening.py` keys it by `job_id` (joins to `results/`), stamps `screened_at`,
and merges without disturbing other entries. The board reads
`screenings/screenings.json` and shows the two badges (BE / ML) on each job.

## Choosing scope

Ask or infer what to screen: a single job the user names, all jobs at one company
(`results/{slug}.json`), or a batch (e.g. all not-yet-screened jobs, or all Tier 1–2).
Screening fetches a JD per job and uses model reasoning, so for big batches prefer the
most relevant subset first and tell the user what you covered / deferred.

**Each job has a `screened` boolean in `results/{slug}.json`** — `false` until it's
been screened. `save_screening.py` flips it to `true` automatically. To screen only the
backlog, list the unscreened jobs:
```bash
python3 -c "import json,glob; [print(d['slug'],j['job_id'],j['title']) for f in glob.glob('results/*.json') for d in [json.load(open(f))] for j in d['jobs'] if not j.get('screened')]"
```

## Invariants

- Screen **both** profiles for every job (unless a profile file is missing).
- Base every judgment on the **actual fetched JD** and the **actual resume** — never
  invent requirements or experience. `fixes` must be truthful surfacing, not lies.
- `job_id` must match the one in `results/` exactly (that's the join key).
- Idempotent: re-screening a job overwrites its entry.

## Later (phase D, not now)

A Python + Claude-API batch scorer (`screen_resume.py`) to score every job in
`results/` unattended, and PDF parse-ability checks (C fidelity) using the `.pdf`.
