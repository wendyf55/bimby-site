"""
Build data/observations.json from the butterfly occurrence dataset.

Current source (switched in 2026-10-05):
    Occurrence records compiled for
    Shepard, J., & Guppy, C. (2001). Butterflies of British Columbia: Including
    Western Alberta, Southern Yukon, the Alaska Panhandle, Washington, Northern
    Oregon, Northern Idaho, and Northwestern Montana. UBC Press.
    File: data/occurrence_data_subset.csv (exported from Occurrence_data-subset.numbers)
    Columns: (row number), Species_binomial, Latitude, Longitude, Date (YYYY-MM-DD)

The previous iNaturalist BIMBY export is kept in data/observations-782254.csv/ and
the old build output in data/observations-inat-2026-09.json.

Usage (from the repo root):
    python3 scripts/build_observations.py

To re-export the CSV from the Numbers file (needs `pip install numbers-parser`):
    python3 scripts/build_observations.py --from-numbers Occurrence_data-subset.numbers

After rebuilding, re-run scripts/build_ecoregions.py (ecoregion lookup) and
scripts/build_species_info.py (descriptions/photos for any new species).
"""
import csv, json, os, sys

SRC = "data/occurrence_data_subset.csv"
OUT = "data/observations.json"
SPECIES_INFO = "data/species-info.json"
OLD_INAT = "data/observations-inat-2026-09.json"

# The dataset has scientific names only. Common names come from species-info.json /
# the old iNat data where the names match; these cover the rest (edit freely).
COMMON_NAMES = {
    "Carterocephalus mandan-skada": "Arctic Skipper",
    "Celastrina echo-asheri": "Echo Azure",
    "Cupido amyntula-comyntas": "Tailed-Blue",
    "Plebejus scudderii": "Scudder's Blue",
}


def export_numbers(path):
    from numbers_parser import Document
    table = Document(path).sheets[0].tables[0]
    with open(SRC, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for row in table.rows(values_only=True):
            w.writerow(row)
    print(f"Exported {table.num_rows - 1} rows -> {SRC}")


def known_common_names():
    names = {}
    if os.path.exists(OLD_INAT):
        for o in json.load(open(OLD_INAT, encoding="utf-8")):
            if o.get("commonName"):
                names.setdefault(o["scientificName"], o["commonName"])
    if os.path.exists(SPECIES_INFO):
        for sci, e in json.load(open(SPECIES_INFO, encoding="utf-8")).get("species", {}).items():
            if e.get("commonName"):
                names[sci] = e["commonName"]
    names.update(COMMON_NAMES)
    return names


def main():
    if "--from-numbers" in sys.argv:
        export_numbers(sys.argv[sys.argv.index("--from-numbers") + 1])

    names = known_common_names()
    rows, skipped, no_name = [], 0, set()
    with open(SRC, newline="", encoding="utf-8") as f:
        for i, r in enumerate(csv.DictReader(f), start=1):
            sci = (r.get("Species_binomial") or "").strip()
            lat = (r.get("Latitude") or "").strip()
            lng = (r.get("Longitude") or "").strip()
            if not (lat and lng and sci):   # skip rows missing essentials
                skipped += 1
                continue
            common = names.get(sci, "")
            if not common:
                no_name.add(sci)
            rows.append({
                "id": i,                                   # row number in the source file
                "scientificName": sci,
                "commonName": common,
                "lat": round(float(lat), 4),   # ~10 m; source is coarser anyway
                "lng": round(float(lng), 4),
                "observedOn": (r.get("Date") or "").strip()[:10],
            })
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {len(rows)} records, {len({r['scientificName'] for r in rows})} species "
          f"-> {OUT} ({os.path.getsize(OUT)//1024} KB); skipped {skipped}")
    if no_name:
        print("No common name for:", ", ".join(sorted(no_name)))


if __name__ == "__main__":
    main()
