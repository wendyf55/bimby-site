"""
cleans the bimby nectaring data (data/BIMBY-butterflies-plants.csv) into
data/plant-visits-clean.csv: one row per butterfly seen on a plant.

Steps:
  1. Keep bc only.
  2. Keep research-grade records only, for both the butterfly and the plant.
  3. Keep licences the site already uses: CC0, CC BY, CC BY-NC.
  4. Keep plants identified to species (drop genus, family, etc.), and drop
     records whose "plant" is rnot a plant
  5. Match butterfly names to the names used on the site: subspecies are rolled
     up to their species, then scripts/inat_name_map.json is applied.
  6. Add common names: butterflies from the site's own data, plants from
     iNaturalist (saved in data/plant-common-names.json, so they are fetched once).
  7. Add each plant's status in BC (native, introduced, ...) from vascan
activity column is dropped

Usage (from the repo root; fetching plant common names needs internet):
    python3 scripts/clean_plant_visits.py
"""
import csv
import json
import os
import time
import urllib.parse
import urllib.request

from vascan import Vascan

SRC = "data/BIMBY-butterflies-plants.csv"
OUT = "data/plant-visits-clean.csv"
PLANT_NAMES = "data/plant-common-names.json"
BUTTERFLY_NAME_MAP = "scripts/inat_name_map.json"
SITE_SPECIES_FILES = ["data/observations-sg.json", "data/observations-inat.json"]

LICENCES = {"CC0", "CC-BY", "CC-BY-NC"}
INAT_API = "https://api.inaturalist.org/v1/taxa"
BC_PLACE_ID = 7085   # asks iNaturalist for the names used in BC

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


def add_plant_bc_status(plants):
    """Returns {scientific name: status in BC} from the VASCAN archive (see scripts/vascan.py).
    Status is '' when VASCAN doesn't know the name."""
    vascan = Vascan()
    return {plant: vascan.bc_status(plant) for plant in plants}


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
    if not row["family"].endswith("aceae"):
        return "'plant' is an animal (e.g. the butterfly itself)"   # plant families end in -aceae
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
