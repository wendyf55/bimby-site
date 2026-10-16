"""
Build data/observations-sg.json (the Guppy & Shepard source) from the occurrence dataset.
The file format is described in scripts/source_files.py; ecoregions are tagged here.

Current source (switched in 2026-10-05):
    Occurrence records compiled for
    Guppy, C., & Shepard, J. (2001). Butterflies of British Columbia: Including
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
import csv, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import source_files

SRC = "data/occurrence_data_subset.csv"
OUT = "data/observations-sg.json"

# The dataset has scientific names only, so its common names live here (edit freely).
# A species not listed falls back to data/species-info.json; the build prints any with no name.
COMMON_NAMES = {
    "Aglais milberti": "Milbert's Tortoiseshell",
    "Anthocharis julia": "Julia Orangetip",
    "Argynnis hydaspe": "Hydaspe Fritillary",
    "Argynnis mormonia": "Mormon Fritillary",
    "Boloria epithore": "Pacific Fritillary",
    "Callophrys augustinus": "Brown Elfin",
    "Callophrys eryphon": "Western Pine Elfin",
    "Callophrys gryneus": "Juniper Hairstreak",
    "Carterocephalus mandan-skada": "Arctic Skipper",
    "Celastrina echo-asheri": "Echo Azure",
    "Cercyonis oetus": "Small Wood-Nymph",
    "Cercyonis pegala": "Common Wood-Nymph",
    "Chlosyne palla": "Northern Checkerspot",
    "Coenonympha california": "Common Ringlet",
    "Colias philodice": "Clouded Sulphur",
    "Cupido amyntula-comyntas": "Tailed-Blue",
    "Erebia epipsodea": "Common Alpine",
    "Erynnis icelus": "Dreamy Duskywing",
    "Erynnis persius": "Persius Duskywing",
    "Euphydryas anicia": "Anicia Checkerspot",
    "Glaucopsyche lygdamus": "Silvery Blue",
    "Hesperia colorado": "American Branded Skipper",
    "Icaricia icarioides": "Boisduval's Blue",
    "Icaricia saepiolus": "Greenish Blue",
    "Limenitis arthemis": "Red-spotted Admiral",
    "Limenitis lorquini": "Lorquin's Admiral",
    "Neophasia menapia": "Pine White",
    "Nymphalis antiopa": "Mourning Cloak",
    "Nymphalis californica": "California Tortoiseshell",
    "Nymphalis l-album": "Compton Tortoiseshell",
    "Ochlodes sylvanoides": "Woodland Skipper",
    "Papilio canadensis": "Canadian Tiger Swallowtail",
    "Papilio eurymedon": "Pale Swallowtail",
    "Papilio rutulus": "Western Tiger Swallowtail",
    "Papilio zelicaon": "Anise Swallowtail",
    "Phyciodes mylitta": "Mylitta Crescent",
    "Phyciodes pulchella": "Field Crescent",
    "Pieris marginalis": "Margined White",
    "Pieris rapae": "Small White",
    "Plebejus scudderii": "Scudder's Blue",
    "Polygonia faunus": "Green Comma",
    "Polygonia gracilis": "Hoary Comma",
    "Polygonia satyrus": "Satyr Comma",
    "Pontia occidentalis": "Western White",
    "Strymon melinus": "Gray Hairstreak",
    "Tharsalea helloides": "Purplish Copper",
    "Tharsalea mariposa": "Mariposa Copper",
    "Thymelicus lineola": "Essex Skipper",
    "Vanessa atalanta": "Red Admiral",
    "Vanessa cardui": "Painted Lady",
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
    """COMMON_NAMES, with species-info.json filling in any species not listed."""
    return source_files.known_common_names(COMMON_NAMES)


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
    source_files.write_source(OUT, "sg", "Guppy & Shepard", rows)
    print(f"Skipped {skipped} rows missing a name or coordinates")
    if no_name:
        print("No common name for:", ", ".join(sorted(no_name)))


if __name__ == "__main__":
    main()
