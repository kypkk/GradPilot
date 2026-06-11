# Resume profiles (input for the `resume-screen` skill)

Drop your two resume profiles here, as `.tex` or `.pdf` (when both exist the skill
reads the `.tex` — cleaner to parse; the `.pdf` is your actual submitted file, also
used for parse-ability checks in a later phase).

| Profile key | Files | For |
|---|---|---|
| `backend-infra` | `backend-infra.tex` and/or `backend-infra.pdf` | Backend / Infrastructure roles |
| `ai-mlops` | `ai-mlops.tex` and/or `ai-mlops.pdf` | AI Engineer / MLOps roles |

The skill screens **every job against both profiles** and writes the scores/badges
to `../screenings/screenings.json` (keyed by `job_id`).

Filenames must match the profile keys above so the skill and the board badges line up.
