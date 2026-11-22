"""
Build data/inat-recent.json: the 5 most recent butterfly sightings in BC on
iNaturalist, with a photo and its credit, for the home page

Same filters as the main pull (scripts/fetch_inat.py)

Names are cleaned the same way as scripts/build_inat.py

File format:
    {
      "built": "2026-11-21",
      "observations": [
        {"id": 123, "sci": "Vanessa cardui", "common": "Painted Lady",
         "date": "2026-11-18", "photo": "https://.../small.jpg",
         "credit": "(c) Jane Doe, some rights reserved (CC BY-NC)"}, ...
      ]
    }
`credit` is iNaturalist's own attribution text for the photo.

Standard library only. Run from the repo root:
    python3 scripts/fetch_inat_recent.py
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import source_files
from fetch_inat import API, LICENSES, QUERY, USER_AGENT

OUT = "data/inat-recent.json"
NAME_MAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inat_name_map.json")
HOW_MANY = 5
BELOW_SPECIES = {"subspecies", "variety", "form", "infrahybrid"}


def fetch_latest():
    """The newest research-grade observations with a reusable photo (a few extra, some get skipped)."""
    params = {k: v for k, v in QUERY.items() if k not in ("order_by", "order", "per_page")}
    params.update({"photos": "true", "photo_license": ",".join(LICENSES),
                   "order_by": "observed_on", "order": "desc", "per_page": 30})
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)["results"]


def main():
    name_map = {k: v for k, v in json.load(open(NAME_MAP)).items() if not k.startswith("_")}
    site_names = source_files.known_common_names()

    picked = []
    for o in fetch_latest():
        t = o.get("taxon") or {}
        name, rank = (t.get("name") or "").strip(), t.get("rank")
        if (o.get("license_code") or "").lower() not in LICENSES or not o.get("observed_on"):
            continue
        if rank in BELOW_SPECIES:
            name = " ".join(name.split()[:2])
        elif rank != "species" and name not in name_map:
            continue   # identified only above species
        if "×" in name:
            continue   # hybrid
        # first photo with a reusable licence
        photo = next((p for p in o.get("photos", [])
                      if (p.get("license_code") or "").lower() in LICENSES and p.get("url")), None)
        if not photo:
            continue
        sci = name_map.get(name, name)
        picked.append({
            "id": o["id"],
            "sci": sci,
            "common": site_names.get(sci) or t.get("preferred_common_name") or "",
            "date": o["observed_on"],
            "photo": photo["url"].replace("/square.", "/small."),
            "credit": photo.get("attribution") or "",
        })
        if len(picked) == HOW_MANY:
            break

    if not picked:
        sys.exit("Nothing found; keeping the old file.")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"built": date.today().isoformat(), "observations": picked}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Wrote {len(picked)} recent sightings to {OUT}:")
    for p in picked:
        print(f"  {p['date']}  {p['common'] or p['sci']}  ({p['credit']})")


if __name__ == "__main__":
    main()
