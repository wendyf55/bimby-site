"""
Build data/observations-inat.json (the iNaturalist source) from the cache written
by scripts/fetch_inat.py. File format: see scripts/source_files.py.

Cleaning
    - Subspecies / varieties / forms are rolled up to their species
      (e.g. Vanessa atalanta rubria -> Vanessa atalanta), then
      scripts/inat_name_map.json merges iNaturalist's split taxa into the lumped
      names Guppy & Shepard use (e.g. Celastrina echo -> Celastrina echo-asheri).
    - Records identified only above species (genus, complex...) and hybrids are left out,
      unless the name is in the name map.
    - Records with poor location accuracy (> 5 km) are left out, except obscured
      ones: those are kept and flagged, and the page leaves them out of the
      small "Near you" distances.
    - Only observations licensed CC0, CC BY or CC BY-NC are used (fetch_inat.py
      already asks for just those; this is a second check). The licence mix is
      printed at the end.
Common names come from data/species-info.json where it has one, otherwise from
iNaturalist (the species-level name, not a subspecies name).

Needs shapely >= 2. Run from the repo root:
    python3 scripts/build_inat.py
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import source_files
from fetch_inat import CACHE, LICENSES, STATE, load_cache

OUT = "data/observations-inat.json"
NAME_MAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inat_name_map.json")
BELOW_SPECIES = {"subspecies", "variety", "form", "infrahybrid"}
MAX_ACCURACY_M = 5000
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def main():
    cache = load_cache()
    if not cache:
        sys.exit(f"No cache at {CACHE}; run scripts/fetch_inat.py first.")
    if not any("license" in r for r in cache.values()):
        sys.exit("The cache predates the licence filter (no licence codes); "
                 "run scripts/fetch_inat.py first (it will do a full pull).")
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    name_map = {k: v for k, v in json.load(open(NAME_MAP)).items() if not k.startswith("_")}
    site_names = source_files.known_common_names()

    rows, dropped, licenses = [], collections.Counter(), collections.Counter()
    inat_common = {}
    for r in cache.values():
        if r.get("license") not in LICENSES:
            dropped["not licensed for reuse (or licence unknown)"] += 1; continue
        name, rank = (r.get("name") or "").strip(), r.get("rank")
        if not name:
            dropped["no name"] += 1; continue
        if rank in BELOW_SPECIES:
            name = " ".join(name.split()[:2])
        elif rank != "species" and name not in name_map:
            dropped["identified above species / hybrid"] += 1; continue
        if "×" in name:
            dropped["identified above species / hybrid"] += 1; continue
        sci = name_map.get(name, name)
        if r.get("lat") is None or r.get("lng") is None:
            dropped["no coordinates"] += 1; continue
        if not r.get("obscured") and (r.get("acc") or 0) > MAX_ACCURACY_M:
            dropped[f"location accuracy > {MAX_ACCURACY_M // 1000} km"] += 1; continue
        if not DATE.match(r.get("date") or ""):
            dropped["no date"] += 1; continue
        if rank == "species" and r.get("common") and sci == name:
            inat_common.setdefault(sci, r["common"])
        licenses[r["license"]] += 1
        rows.append({"id": r["id"], "sci": sci, "lat": r["lat"], "lng": r["lng"],
                     "date": r["date"], "obscured": r.get("obscured")})
    for row in rows:
        row["common"] = site_names.get(row["sci"]) or inat_common.get(row["sci"], "")

    source_files.write_source(OUT, "inat", "iNaturalist", rows, as_of=state.get("lastRun"))
    print("Licences:", ", ".join(f"{k.upper()} {n}" for k, n in licenses.most_common()))
    print(f"Obscured locations (kept, flagged): {sum(1 for r in rows if r['obscured'])}")
    for why, n in dropped.most_common():
        print(f"Left out, {why}: {n}")
    no_common = sorted({r['sci'] for r in rows if not r['common']})
    if no_common:
        print("No common name for:", ", ".join(no_common))


if __name__ == "__main__":
    main()
