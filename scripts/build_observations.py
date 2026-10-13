"""
Build data/observations-sg.json (the Shepard & Guppy source) from the occurrence dataset.
The file format is described in scripts/bimby_data.py; ecoregions are tagged here.

Current source (switched in 2026-10-05):
    Occurrence records compiled for
    Shepard, J., & Guppy, C. (2001). Butterflies of British Columbia: Including
    Western Alberta, Southern Yukon, the Alaska Panhandle, Washington, Northern
    Oregon, Northern Idaho, and Northwestern Montana. UBC Press.
    File: data/occurrence_data_subset.csv (exported from Occurrence_data-subset.numbers)
    Columns: (row number), Species_binomial, Latitude, Longitude, Date (YYYY-MM-DD)

iNaturalist records are a separate source: scripts/fetch_inat.py + scripts/build_inat.py.

Usage (from the repo root):
    python3 scripts/build_observations.py

To re-export the CSV from the Numbers file (needs `pip install numbers-parser`):
    python3 scripts/build_observations.py --from-numbers Occurrence_data-subset.numbers

Needs shapely >= 2 (pip install shapely). Afterwards run scripts/build_species_info.py
to fetch descriptions/photos for any new species.
"""
import csv, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bimby_data

SRC = "data/occurrence_data_subset.csv"
OUT = "data/observations-sg.json"
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
    names.update(bimby_data.known_common_names(COMMON_NAMES))
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
                "sci": sci,
                "common": common,
                "lat": float(lat),
                "lng": float(lng),
                "date": (r.get("Date") or "").strip()[:10],
            })
    bimby_data.write_source(OUT, "sg", "Shepard & Guppy", rows)
    print(f"Skipped {skipped} rows missing a name or coordinates")
    if no_name:
        print("No common name for:", ", ".join(sorted(no_name)))


if __name__ == "__main__":
    main()
