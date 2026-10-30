"""
Clean the butterfly-on-plant records (data/BIMBY-butterflies-plants.csv) into
data/plant-visits-clean.csv, one row per butterfly seen on a plant.

Steps:
  1. Keep British Columbia only.
  2. Keep research-grade records only, for both the butterfly and the plant.
  3. Keep licences the site already uses: CC0, CC BY, CC BY-NC.
  4. Keep plants identified to species (drop genus, family, etc.).
  5. Match butterfly names to the names used on the site: subspecies are rolled
     up to their species, then scripts/inat_name_map.json is applied.
  6. Add common names: butterflies from the site's own data, plants from
     iNaturalist (saved in data/plant-common-names.json, so they are fetched once).
  7. Add each plant's status in BC (native, introduced, ...) from VASCAN, the
     Database of Vascular Plants of Canada (saved in data/plant-bc-status.json).
The "activity" column dropped

Usage (from the repo root; fetching plant names and statuses needs internet):
    python3 scripts/clean_plant_visits.py
"""
import csv
import json
import os
import time
import urllib.parse
import urllib.request

SRC = "data/BIMBY-butterflies-plants.csv"
OUT = "data/plant-visits-clean.csv"
PLANT_NAMES = "data/plant-common-names.json"
PLANT_STATUS = "data/plant-bc-status.json"
BUTTERFLY_NAME_MAP = "scripts/inat_name_map.json"
SITE_SPECIES_FILES = ["data/observations-sg.json", "data/observations-inat.json"]

LICENCES = {"CC0", "CC-BY", "CC-BY-NC"}
INAT_API = "https://api.inaturalist.org/v1/taxa"
BC_PLACE_ID = 7085   # asks iNaturalist for the names used in BC
VASCAN_API = "https://data.canadensys.net/vascan/api/0.1/search.json"
VASCAN_BATCH = 200   # VASCAN accepts up to 200 names per request

COLUMNS = [
    "id", "date", "latitude", "longitude", "obscured",
    "butterfly", "butterfly_common", "plant", "plant_common", "plant_family", "bc_status",
    "user_id", "license", "url", "image_url",
]


def load_butterfly_names():
    """Returns (name_map, common_names) for butterflies.

    name_map: iNaturalist name -> name used on the site.
    common_names: site name -> common name, taken from the site's own data files."""
    name_map = json.load(open(BUTTERFLY_NAME_MAP))
    name_map = {k: v for k, v in name_map.items() if not k.startswith("_")}
    common_names = {}
    for path in SITE_SPECIES_FILES:
        for sci, common in json.load(open(path))["species"]:
            common_names.setdefault(sci, common)
    return name_map, common_names


def site_butterfly_name(name, name_map):
    """'Argynnis cybele leto' -> 'Argynnis cybele'; then apply the name map."""
    species = " ".join(name.split()[:2])
    return name_map.get(species, species)


def fetch_plant_common_name(sci):
    """Asks iNaturalist for a plant's English common name ('' if none)."""
    query = urllib.parse.urlencode({
        "q": sci, "rank": "species", "locale": "en", "preferred_place_id": BC_PLACE_ID,
    })
    with urllib.request.urlopen(f"{INAT_API}?{query}", timeout=30) as response:
        results = json.load(response)["results"]
    for taxon in results:
        if taxon["name"] == sci:
            return taxon.get("preferred_common_name", "")
    return ""


def add_plant_common_names(plants):
    """Returns {scientific name: common name}, fetching any not already saved."""
    names = json.load(open(PLANT_NAMES)) if os.path.exists(PLANT_NAMES) else {}
    missing = sorted(p for p in plants if p not in names)
    if missing:
        print(f"Fetching common names for {len(missing)} plants from iNaturalist...")
    for i, sci in enumerate(missing, 1):
        try:
            names[sci] = fetch_plant_common_name(sci)
        except OSError as error:
            print(f"  Could not reach iNaturalist ({error}); stopping. Run again to continue.")
            break
        if i % 25 == 0:
            print(f"  {i} of {len(missing)}")
        time.sleep(1)   # be polite to the iNaturalist API
    with open(PLANT_NAMES, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(names.items())), f, indent=2, ensure_ascii=False)
    return names


def ask_vascan(terms):
    """Looks up names (or VASCAN taxon ids) in VASCAN. Returns its list of results,
    one per term, in the same order."""
    body = urllib.parse.urlencode({"q": "\n".join(str(t) for t in terms)}).encode()
    with urllib.request.urlopen(VASCAN_API, data=body, timeout=60) as response:
        return json.load(response)["results"]


def bc_status_of(match):
    """'native', 'introduced', 'ephemeral', ... for BC, or 'absent' if not listed in BC."""
    for place in match.get("distribution", []):
        if place["locality"] == "BC":
            return place["occurrenceStatus"]
    return "absent"


def is_accepted(match):
    return match["taxonomicAssertions"][0]["taxonomicStatus"] == "accepted"


def add_plant_bc_status(plants):
    """Returns {scientific name: status in BC}, fetching any not already saved.
    Status is '' when VASCAN doesn't know the name."""
    statuses = json.load(open(PLANT_STATUS)) if os.path.exists(PLANT_STATUS) else {}
    missing = sorted(p for p in plants if p not in statuses)
    if missing:
        print(f"Fetching BC status for {len(missing)} plants from VASCAN...")
    try:
        for start in range(0, len(missing), VASCAN_BATCH):
            batch = missing[start:start + VASCAN_BATCH]
            synonyms = {}   # our name -> VASCAN id of the accepted name
            for name, result in zip(batch, ask_vascan(batch)):
                # VASCAN leaves out "matches" when it finds nothing
                matches = [m for m in result.get("matches", []) if m.get("canonicalName") == name]
                accepted = [m for m in matches if is_accepted(m)]
                if accepted:
                    statuses[name] = bc_status_of(accepted[0])
                elif matches:
                    # An older name: look up the name VASCAN uses now.
                    synonyms[name] = matches[0]["taxonomicAssertions"][0]["acceptedNameUsageID"]
                else:
                    statuses[name] = ""
            if synonyms:
                for name, result in zip(synonyms, ask_vascan(synonyms.values())):
                    matches = result.get("matches", [])
                    statuses[name] = bc_status_of(matches[0]) if matches else ""
            time.sleep(1)
    except OSError as error:
        print(f"  Could not reach VASCAN ({error}); run again to finish.")
    not_found = [p for p in plants if statuses.get(p) == ""]
    if len(not_found) > len(plants) / 2:
        print(f"  Warning: VASCAN found only {len(plants) - len(not_found)} of {len(plants)} plants.")
        print("  What VASCAN sent back for the first one:")
        print("  ", json.dumps(ask_vascan(not_found[:1])[0])[:600])
        print(f"  Not saving these results, so the next run asks again.")
        return statuses
    with open(PLANT_STATUS, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(statuses.items())), f, indent=2, ensure_ascii=False)
    return statuses


def capitalize(name):
    """'common yarrow' -> 'Common yarrow' (names come in mixed case)."""
    return name[:1].upper() + name[1:]


def is_kept(row):
    """Returns the reason a row is dropped, or None if it is kept."""
    if row["place_state_name"] != "British Columbia":
        return "outside BC"
    if row["quality_grade"] != "research":
        return "butterfly not research grade"
    if row["status"] != "Research Grade":
        return "plant not research grade"
    if row["license"] not in LICENCES:
        return "licence"
    if row["species"] in ("", "NA"):
        return "plant not identified to species"
    if len(row["scientific_name"].split()) < 2:
        return "butterfly not identified to species"
    return None


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    name_map, butterfly_common = load_butterfly_names()

    kept, dropped = [], {}
    for row in rows:
        reason = is_kept(row)
        if reason:
            dropped[reason] = dropped.get(reason, 0) + 1
        else:
            kept.append(row)

    plants = {row["species"] for row in kept}
    plant_common = add_plant_common_names(plants)
    plant_status = add_plant_bc_status(plants)

    out = []
    not_on_site = {}
    for row in kept:
        butterfly = site_butterfly_name(row["scientific_name"], name_map)
        if butterfly not in butterfly_common:
            not_on_site[butterfly] = not_on_site.get(butterfly, 0) + 1
        out.append({
            "id": row["id"],
            "date": row["observed_on"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "obscured": "1" if row["coordinates_obscured"] == "TRUE" else "0",
            "butterfly": butterfly,
            "butterfly_common": butterfly_common.get(butterfly, row["common_name"]),
            "plant": row["species"],
            "plant_common": capitalize(plant_common.get(row["species"], "")),
            "plant_family": row["family"],
            "bc_status": plant_status.get(row["species"], ""),
            "user_id": row["user_id"],
            "license": row["license"],
            "url": row["url"],
            "image_url": row["image_url"],
        })

    out.sort(key=lambda r: int(r["id"]))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(out)

    # Summary
    print(f"\nRead {len(rows)} records, wrote {len(out)} to {OUT}")
    print("Dropped:")
    for reason, count in sorted(dropped.items(), key=lambda x: -x[1]):
        print(f"  {count:6}  {reason}")
    print(f"{len({r['butterfly'] for r in out})} butterfly species, "
          f"{len({r['plant'] for r in out})} plant species")
    no_name = sorted({r["plant"] for r in out if not r["plant_common"]})
    print(f"{len(no_name)} plants without a common name")
    counts = {}
    for plant in {r["plant"] for r in out}:
        status = plant_status.get(plant, "") or "not found in VASCAN"
        counts[status] = counts.get(status, 0) + 1
    print("Plant species by status in BC:", ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    if not_on_site:
        print("Butterflies not in the site's species list (kept, using iNaturalist's common name):")
        for name, count in sorted(not_on_site.items(), key=lambda x: -x[1]):
            print(f"  {count:6}  {name}")


if __name__ == "__main__":
    main()
