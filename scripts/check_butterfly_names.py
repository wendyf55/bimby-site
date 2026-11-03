"""
Check the butterfly name matches in scripts/deedes_name_map.json against
iNaturalist's taxonomy, and write a table to review: data/deedes-name-check.csv.

For every butterfly Latin name in data/hosts-Deedes.xlsx, asks iNaturalist which
taxon that name belongs to today (iNaturalist keeps old names as synonyms), then
compares it with the site name the map gives. Lumped site names
(scripts/inat_name_map.json, e.g. "Celastrina echo" -> "Celastrina echo-asheri")
are applied first, so they count as agreeing.

The "inat" column says how iNaturalist matched the name:
  current     the name is iNaturalist's current name
  synonym     an older name; iNaturalist files it under the current name shown
  replaced    an inactive taxon; iNaturalist points to the taxon that replaced it
  not found   iNaturalist doesn't know the name
Misspelled names are looked up with the spelling given under "spelling" in the map.
"agrees" is yes / no / check (not found, or iNaturalist gives more than one taxon).

    python3 scripts/check_butterfly_names.py
"""
import csv
import json
import time
import urllib.parse
import urllib.request

from clean_hosts_deedes import read_list

NAME_MAP = "scripts/deedes_name_map.json"
INAT_NAME_MAP = "scripts/inat_name_map.json"
OUT = "data/deedes-name-check.csv"
API = "https://api.inaturalist.org/v1"
BUTTERFLIES = 47224   # iNaturalist taxon id for butterflies (Papilionoidea)
HEADERS = {"User-Agent": "bimby-site name check"}


def get(path, **params):
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["results"]


def species_of(taxon):
    """Species name for a species or subspecies taxon ('Papilio zelicaon nitra' -> 'Papilio zelicaon')."""
    return " ".join(taxon["name"].split()[:2])


def look_up(name):
    """Returns (how matched, list of current taxa) for a Latin name."""
    results = get("taxa", q=name, taxon_id=BUTTERFLIES, is_active="any", per_page=30)
    exact = [t for t in results
             if t["name"].lower() == name.lower() or (t.get("matched_term") or "").lower() == name.lower()]
    if not exact:
        return "not found", []
    how, current = set(), []
    for t in exact:
        if t["is_active"] and t["name"].lower() == name.lower():
            how.add("current"); current.append(t)
        elif t["is_active"]:
            how.add("synonym"); current.append(t)
        else:
            how.add("replaced")
            for new_id in t.get("current_synonymous_taxon_ids") or []:
                current += get(f"taxa/{new_id}")
                time.sleep(1)
    return " + ".join(sorted(how)), current


def main():
    name_map = json.load(open(NAME_MAP))
    names, spelling = name_map["butterflies"], name_map.get("spelling", {})
    lumps = {k: v for k, v in json.load(open(INAT_NAME_MAP)).items() if not k.startswith("_")}
    listed = {}
    for row in read_list():
        listed.setdefault(row["ButterflyLatinName"], row["ButterflyEnglishName"])

    out = []
    for i, (name, common) in enumerate(listed.items(), 1):
        mapped = names.get(name, " ".join(name.split()[:2]))
        mapped = mapped if isinstance(mapped, list) else [mapped]
        try:
            how, taxa = look_up(spelling.get(name, name))
        except OSError as error:
            print(f"Could not reach iNaturalist ({error}); stopping.")
            break
        inat_species = sorted({lumps.get(species_of(t), species_of(t)) for t in taxa})
        if not taxa or len(inat_species) > 1:
            agrees = "check"
        else:
            agrees = "yes" if inat_species == sorted(m for m in mapped if m) else "no"
        out.append({
            "list_name": name, "list_common": common, "checked_as": spelling.get(name, name),
            "my_match": "; ".join(m or "(left out)" for m in mapped),
            "inat": how, "inat_name": "; ".join(inat_species),
            "inat_common": "; ".join(sorted({t.get("preferred_common_name", "") for t in taxa})),
            "agrees": agrees,
            "inat_url": "; ".join(f"https://www.inaturalist.org/taxa/{t['id']}" for t in taxa),
        })
        if i % 20 == 0:
            print(f"  {i} of {len(listed)}")
        time.sleep(1)   # be polite to the iNaturalist API

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    counts = {}
    for r in out:
        counts[r["agrees"]] = counts.get(r["agrees"], 0) + 1
    print(f"Wrote {len(out)} names to {OUT}: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    for r in out:
        if r["agrees"] != "yes":
            print(f"  {r['agrees']:5}  {r['list_name']} ({r['list_common']}) -> mine: {r['my_match']}; "
                  f"iNat ({r['inat']}): {r['inat_name'] or '-'}")


if __name__ == "__main__":
    main()
