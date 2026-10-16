# Butterflies of BC

A citizen-science map of BC.

## TODO

- update place searching? Nominatim limited to one request / second, but that could be fine
- deduplicate - how?
- fetch-inat.py can lose its progress
- redeploy with GH pages

## Running locally

This site must be served over HTTP (not opened as a file), because it uses `fetch()`
to load the data files. From the repo root:

    python3 -m http.server 8000

Then open <http://localhost:8000>

The Python scripts in `scripts/` need a few packages (Python 3.10+):

    pip install -r requirements.txt

## Repository structure

    index.html                     Page structure; loads the files below
    styles.css                     All the styling
    app.js                         The app: map, place search, butterfly lists, charts, shareable links
    species-info.js                Species photos + descriptions (thumbnails and detail cards)
    requirements.txt               Python packages for the scripts
    .github/workflows/
      update-inat.yml              Refreshes the iNaturalist data on Mondays and Thursdays
    data/                          Git-ignored, except the files the site and the weekly job need (*)
      observations-sg.json         * Guppy & Shepard records, in the format the page loads (generated)
      observations-inat.json       * iNaturalist records, in the format the page loads (generated)
      inat/state.json              * When the iNaturalist data was last pulled. The raw download
                                     (inat/cache.jsonl) is kept in the GitHub Actions cache, not in git
      occurrence_data_subset.csv   Guppy & Shepard occurrence data (CSV export of the .numbers file)
      plant-lists.json             * Host/nectar plant lists, one entry per region/source
      ecoregions.geojson           * Simplified ecoregion outlines (generated)
      ecozones.geojson             Ecozone outlines (generated; not currently used)
      species-info.json            * Species descriptions + photos (generated)
      species-info-overrides.json  * Optional hand fixes for the above
      postal-fsa.json              * BC postal code areas for the place search (generated)
      raw/                         Ecoregion + ecozone shapefile zips from AAFC,
                                   FSA boundary zip from Statistics Canada
    scripts/
      source_files.py              Shared by the source builders: ecoregion tagging, common names,
                                   writing data/observations-<source>.json
      build_observations.py        Builds observations-sg.json from the occurrence CSV
      fetch_inat.py                Downloads iNaturalist observations into data/inat/cache.jsonl
      build_inat.py                Builds observations-inat.json from that download
      inat_name_map.json           iNaturalist names -> names used on the site (lumped taxa)
      build_ecoregions.py          Builds ecoregions.geojson and ecozones.geojson
      build_species_info.py        Builds species-info.json (needs internet)
      build_postal.py              Builds postal-fsa.json from the FSA boundary file

## Data sources

### Butterfly occurrences — Guppy & Shepard (2001)

- **Source:** Guppy, C., & Shepard, J. (2001). *Butterflies of British Columbia:
  Including Western Alberta, Southern Yukon, the Alaska Panhandle, Washington,
  Northern Oregon, Northern Idaho, and Northwestern Montana.* UBC Press.
- **File:** `Occurrence_data-subset.numbers` (added 2026-10-05), exported to
  `data/occurrence_data_subset.csv`.
- **Contents:** 104,279 records of 50 species, 1950–2025, all in British Columbia;
  every record has coordinates and a date. Most common: Small White (8,384),
  Woodland Skipper (5,386), Lorquin's Admiral (4,871).
- **Fields used:** `Species_binomial`, `Latitude`, `Longitude`, `Date`; `id` is the
  row number. The data has no common names, so `build_observations.py` keeps them in a
  `COMMON_NAMES` table (all 50 species, including the four lumped taxa such as
  *Celastrina echo-asheri*); a species missing from it falls back to `species-info.json`.
- **Pipeline:** `python3 scripts/build_observations.py` (add
  `--from-numbers Occurrence_data-subset.numbers` to re-export the CSV first; that needs
  `numbers-parser`) writes `data/observations-sg.json`, tagging each record's ecoregion.
  Then `scripts/build_species_info.py` for any new species.

### Nectar & host plants — Xerces Society

- **Source:** Adamson, N. L., Fallon, C., & Vaughan, M. (2018).
  *Monarch Butterfly Nectar Plant Lists for Conservation Plantings.*
  The Xerces Society for Invertebrate Conservation. Publication 18-003_02.
- **URL:** <https://xerces.org/sites/default/files/publications/18-003_02_Monarch-Nectar-Plant-Lists-FS_web%20-%20Jessa%20Kay%20Cruz.pdf>

### Ecoregions — National Ecological Framework for Canada

- **Source:** Agriculture and Agri-Food Canada, *A National Ecological Framework for
  Canada* — ecoregion and ecozone shapefiles, from
  <https://sis.agr.gc.ca/cansis/nsdb/ecostrat/gis_data.html> (Open Government Licence – Canada).
- **Contents:** 194 ecoregions (218 polygons) grouped into 15 ecozones, NAD83 lat/long.
- **Raw files:** `data/raw/ecoregion_shp.zip`, `data/raw/ecozone_shp.zip` (downloaded 2026-09-25).
- **Pipeline:** `scripts/build_ecoregions.py` (packages from `requirements.txt`) writes:
  - `data/ecoregions.geojson` — outlines simplified to ~2 km (shared borders kept
    identical), for the map and the "Your ecoregion" view.
  - `data/ecozones.geojson` — the 15 ecozones, merged from the simplified ecoregions
    (so their borders line up exactly). Not used by the page right now.
- **Tagging:** each record's ecoregion is worked out when its source file is built
  (`scripts/source_files.py`), using the same simplified outlines the page uses. Points
  just off the coast snap to the nearest ecoregion within ~5 km, and the page does the
  same for a clicked spot, so the two always agree; a handful of records outside Canada
  are left untagged. If the outlines change, rebuild both sources
  (`build_observations.py`, `build_inat.py`).

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
  header); a species is fetched again whenever its override is added, changed or
  removed. Pages work without the file — they just show no photos/descriptions.
- **On the pages:** a small photo next to each butterfly in the lists, and the photo +
  description at the top of each butterfly's detail view.

### Postal code areas — Statistics Canada FSA boundaries

- **Source:** Statistics Canada, *Census Forward Sortation Area Boundary File, 2021*
  (catalogue 92-179-X), cartographic boundaries, shapefile:
  <https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/files-fichiers/lfsa000b21a_e.zip>
  (Statistics Canada Open Licence).
- **Why only the first three characters:** full six-character postal code locations
  are licensed by Canada Post (and Statistics Canada's Postal Code Conversion File
  can't be redistributed), but forward sortation area (FSA) boundaries — the "V6T" in
  "V6T 1Z4" — are open. City FSAs are a few km across, close enough for a 5 km search.
- **Raw file:** `data/raw/lfsa000b21a_e.zip` (downloaded 2026-10-16, ~160 MB; Statistics
  Canada's site has to be opened in a browser — scripted downloads are refused).
- **Pipeline:** `python3 scripts/build_postal.py` (packages from `requirements.txt`;
  the boundaries are in Statistics Canada Lambert and are reprojected to lat/long)
  writes `data/postal-fsa.json` (~130 KB): one entry per BC FSA (191, all starting
  with V) with a point well inside the area and its size in km². "Wide" FSAs — rural
  codes (second character 0, e.g. V0H) and any larger than 250 km² (52 in all) — also
  carry an outline simplified to ~2 km.
- **On the page:** the place search recognises postal codes ("V6T 1Z4", "v6t1z4",
  "V6T"; a letter O typed for a zero is accepted) and looks them up in this file,
  loaded only on the first postal code search, instead of OpenStreetMap:
  - city FSA → pin at the area's point, labelled with the town, e.g. "Vancouver,
    British Columbia (V6T)";
  - wide FSA → the area is outlined on the map and the visitor is asked to click their
    spot or search their town (a pin in the middle could be far from them);
  - non-BC code → "…is a postal code in Alberta. This map covers British Columbia only";
  - if the file is missing, the search falls back to OpenStreetMap.
- **Town search:** other text goes to OpenStreetMap's Nominatim geocoder, limited to a
  rectangle around BC; results are then filtered to BC by address (the rectangle also
  takes in part of Alberta, e.g. Banff and Jasper).

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
