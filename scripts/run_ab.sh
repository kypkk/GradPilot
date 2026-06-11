#!/bin/bash
# A+B refresh — run manually (or via a schedule you set up) on a machine with
# outbound network. Pulls Simplify + the 4 ATS, then prunes dead links.
# B.5 (Tier 1-2) + C are NOT done here — that's Cowork's browser job.
cd /Users/kangkang/kypkk/2026Fall || exit 1
PY=/opt/homebrew/Caskroom/miniconda/base/bin/python3
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %z') A+B refresh ====="
  "$PY" scripts/fetch_jobs.py
  "$PY" scripts/prune_dead.py
  echo "----- done -----"
} >> refresh.log 2>&1
