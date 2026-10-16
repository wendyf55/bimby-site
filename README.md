# Butterflies of BC

A citizen-science map of BC.

## Running locally

This site must be served over HTTP (not opened as a file), because it uses `fetch()`
to load the data files. From the repo root:

    python3 -m http.server 8000

Then open <http://localhost:8000>

## Repository structure

    index.html                     The whole app (map + interaction)
    species-info.js                Species photos + descriptions, shared by all pages
    data/                          (git-ignored)
      observations.json            Butterfly occurrence records used by the app (generated)
      occurrence_data_subset.csv   Shepard & Guppy occurrence data (CSV export of the .numbers file)
      observations-inat-2026-09.json  Previous app data from the iNat export (backup)
      plant-lists.json             Host/nectar plant lists, one entry per region/source
      observations-782254.csv/     Raw iNaturalist export (previous source, kept for provenance)
      ecoregions.geojson           Simplified ecoregion outlines (generated)
      observation-ecoregions.json  Observation id -> ecoregion id (generated)
      ecozones.geojson             Ecozone outlines (generated; not currently used)
      species-info.json            Species descriptions + photos (generated)
      species-info-overrides.json  Optional hand fixes for the above
      raw/                         Ecoregion + ecozone shapefile zips from AAFC
    scripts/
      build_observations.py        Rebuilds observations.json from the occurrence CSV
      build_ecoregions.py          Builds the three ecoregion/ecozone files above
      build_species_info.py        Builds species-info.json (needs internet)

## Data sources

### Butterfly occurrences — Shepard & Guppy (2001)

- **Source:** Shepard, J., & Guppy, C. (2001). *Butterflies of British Columbia:
  Including Western Alberta, Southern Yukon, the Alaska Panhandle, Washington,
  Northern Oregon, Northern Idaho, and Northwestern Montana.* UBC Press.
- **File:** `Occurrence_data-subset.numbers` (added 2026-10-05), exported to
  `data/occurrence_data_subset.csv`.
- **Contents:** 104,279 records of 50 species, 1950–2025, all in British Columbia;
  every record has coordinates and a date. Most common: Small White (8,384),
  Woodland Skipper (5,386), Lorquin's Admiral (4,871).
- **Fields used:** `Species_binomial`, `Latitude`, `Longitude`, `Date`; `id` is the
  row number. The data has no common names — `build_observations.py` takes them from
  `species-info.json` / the old iNat data, plus a small `COMMON_NAMES` table in the
  script for the four lumped taxa (e.g. *Celastrina echo-asheri*).
- **Pipeline:** `python3 scripts/build_observations.py` (add
  `--from-numbers Occurrence_data-subset.numbers` to re-export the CSV first), then
  `scripts/build_ecoregions.py` and `scripts/build_species_info.py`.

### Nectar & host plants — Xerces Society

- **Source:** Adamson, N. L., Fallon, C., & Vaughan, M. (2018).
  *Monarch Butterfly Nectar Plant Lists for Conservation Plantings.*
  The Xerces Society for Invertebrate Conservation. Publication 18-003_02.
- **URL:** <https://xerces.org/sites/default/files/publications/18-003_02_Monarch-Nectar-Plant-Lists-FS_web%20-%20Jessa%20Kay%20Cruz.pdf>

### Ecoregions — National Ecological Framework for Canada (used by option-a.html and option-b.html)

- **Source:** Agriculture and Agri-Food Canada, *A National Ecological Framework for
  Canada* — ecoregion and ecozone shapefiles, from
  <https://sis.agr.gc.ca/cansis/nsdb/ecostrat/gis_data.html> (Open Government Licence – Canada).
- **Contents:** 194 ecoregions (218 polygons) grouped into 15 ecozones, NAD83 lat/long.
- **Raw files:** `data/raw/ecoregion_shp.zip`, `data/raw/ecozone_shp.zip` (downloaded 2026-09-25).
- **Pipeline:** `scripts/build_ecoregions.py` (needs `pip install pyshp shapely`,
  shapely ≥ 2.1) writes:
  - `data/ecoregions.geojson` — outlines simplified to ~2 km (shared borders kept
    identical), for the map.
  - `data/observation-ecoregions.json` — `{observation id: ecoregion id}`. Points
    just off the coast snap to the nearest ecoregion within ~5 km; a handful outside
    Canada are left untagged.
  - `data/ecozones.geojson` — the 15 ecozones, merged from the simplified ecoregions
    (so their borders line up exactly). Not used by any page right now.

### Species descriptions & photos — Wikipedia + iNaturalist

- **Descriptions:** the first paragraph of each species' English Wikipedia article
  (REST "page summary" API). Wikipedia text is **CC BY-SA 4.0**; every description on
  the site links back to its article with the licence.
- **Photos:** each species' iNaturalist taxon photo (the one on its iNaturalist
  species page). "All rights reserved" photos are skipped in favour of the next openly
  licensed photo iNaturalist has for that species. Licences are mostly CC BY-NC
  (fine for a non-commercial research site); every photo is shown with the
  photographer's credit and licence. If iNaturalist has nothing licensed, the
  Wikipedia lead image is used (credit + licence from Wikimedia Commons).
- **Pipeline:** `python3 scripts/build_species_info.py` (standard library only, needs
  internet, ~5–8 min for ~250 species) writes `data/species-info.json`. Re-running only
  fetches species that are new; `--refresh` re-fetches everything. Wrong or missing
  matches can be fixed by hand in `data/species-info-overrides.json` (see the script's
  header). Pages work without the file — they just show no photos/descriptions.
- **On the pages:** a small photo next to each butterfly in the lists, and the photo +
  description at the top of each butterfly's detail view.

## `plant-lists.json` structure

An array of "lists". Each list is one plant recommendation set, tagged with the
butterfly it applies to, its geographic region, and its source (for attribution and
for the in-app "which list?" selector):

    {
      "id": "monarch-nectar-xerces-maritime-nw",
      "butterfly": { "scientificName": "Danaus plexippus", "commonName": "Monarch" },
      "region": "Maritime Northwest (n.w. CA, w. OR, w. WA)",
      "source": { "org": "...", "title": "...", "authors": [...], "year": 2018, "url": "..." },
      "plants": [
        { "scientificName": "...", "commonName": "...", "bloom": "May–Aug", "isHost": true }
      ]
    }

Adding another region or another source = appending another object to this array.
The app groups lists by butterfly species, so a species with multiple lists gets a
dropdown to choose which to view.
