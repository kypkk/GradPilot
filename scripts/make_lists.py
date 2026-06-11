#!/usr/bin/env python3
"""Regenerate companies.txt + tiers.json from swe-tier-list.html.

swe-tier-list.html's inline `data` object is the single source of truth for the
company list and their tiers. Run this whenever you add/move companies in the HTML
so the fetcher pipeline stays in sync. Stdlib only.

Outputs:
  companies.txt  - one company name per line (tier order)
  tiers.json     - { slug: "Tier 1" | "Tier 1.5" | ... }
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
DATA = os.path.join(ROOT, "data")


def slugify(name):
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", name.lower()))


def main():
    html = open(os.path.join(ROOT, "swe-tier-list.html"), encoding="utf-8").read()
    block = re.search(r"const data = (\{.*?\n\});", html, re.S).group(1)
    names, tiers = [], {}
    for tier, arr in re.findall(r'"(Tier [^"]+)"\s*:\s*\[(.*?)\]', block, re.S):
        for nm in re.findall(r'\bn:"((?:\\.|[^"\\])*)"', arr):
            if "\\" in nm:
                nm = nm.encode().decode("unicode_escape")
            names.append(nm)
            tiers[slugify(nm)] = tier
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "companies.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(names) + "\n")
    with open(os.path.join(DATA, "tiers.json"), "w", encoding="utf-8") as f:
        json.dump({"count": len(names), "tiers": tiers}, f,
                  ensure_ascii=False, indent=2)
    by = {}
    for t in tiers.values():
        by[t] = by.get(t, 0) + 1
    print(f"wrote companies.txt ({len(names)}) + tiers.json  {json.dumps(by)}")


if __name__ == "__main__":
    main()
