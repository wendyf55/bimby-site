# BIMBY — Butterflies In My Backyard

A citizen-science map of BC.

## Running locally

This site must be served over HTTP (not opened as a file), because it uses `fetch()`
to load the data files. From the repo root:

    python3 -m http.server 8000

Then open <http://localhost:8000>

## Repository structure

    index.html                     The whole app: "Your backyard" (location-first map, photo cards)
    species-info.js                Species photos + descriptions
    .github/workflows/update-inat.yml  Weekly iNaturalist refresh (GitHub Actions)
    data/                          (git-ignored, except the files marked *)
      observations-sg.json         Shepard & Guppy records for the app (generated)
      observations-inat.json     * iNaturalist records for the app (generated weekly)
      inat/cache.jsonl           * iNaturalist download cache, one observation per line
      inat/state.json            * When the last pull / last full pull ran
      occurrence_data_subset.csv   Shepard & Guppy occurrence data (CSV export of the .numbers file)
      observations.json, observation-ecoregions.json,
      observations-inat-2026-09.json  Older formats / the Sept 2026 BIMBY export (no longer used)
      plant-lists.json             Host/nectar plant lists, one entry per region/source
      observations-782254.csv/     Raw iNaturalist export (previous source, kept for provenance)
      ecoregions.geojson         * Simplified ecoregion outlines (generated)
      ecozones.geojson             Ecozone outlines (generated; not currently used)
      species-info.json          * Species descriptions + photos (generated)
      species-info-overrides.json  Optional hand fixes for the above
      raw/                         Ecoregion + ecozone shapefile zips from AAFC
    scripts/
      bimby_data.py                Shared: ecoregion tagging + the per-source file format
      build_observations.py        Builds observations-sg.json from the occurrence CSV
      fetch_inat.py                Downloads iNaturalist records into data/inat/ (needs internet)
      build_inat.py                Builds observations-inat.json from that download
      inat_name_map.json           iNaturalist names -> names used on the site
      build_ecoregions.py          Builds ecoregions.geojson / ecozones.geojson
      build_species_info.py        Builds species-info.json (needs internet)

## Data sources on the page

Each source is its own file, `data/observations-<source>.json`, in a compact format
(species table + one row per record, ecoregion already tagged; see `scripts/bimby_data.py`).
The page loads every source it finds and offers a **Data: Both / Shepard & Guppy /
iNaturalist** picker; counts, cards, charts and map dots all follow it, and the choice is
kept in the URL (`#…&src=inat`). A source whose file is missing is simply left out.
To add another source, write a builder that calls `bimby_data.write_source()` and add
it to `SOURCES` near the top of the script in `index.html`.

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
  `--from-numbers Occurrence_data-subset.numbers` to re-export the CSV first; needs
  `pip install shapely`), then `scripts/build_species_info.py`.
- Kept out of git (not ours to publish), so it is only on machines that have the file.

### Butterfly occurrences — iNaturalist (updated weekly)

- **What:** research-grade observations of butterflies (Papilionoidea, taxon 47224) in
  British Columbia (place 7085), from the [iNaturalist API](https://api.inaturalist.org/v1/docs/).
  Research grade = date, location, photo, and a species-level ID agreed by the community.
- **Fetching** (`scripts/fetch_inat.py`, standard library only): follows iNaturalist's
  [API recommended practices](https://www.inaturalist.org/pages/api+recommended+practices).
  It pages by id (`order_by=id&id_above=…`, 200 per request) because the API stops at
  10,000 results with page numbers; it makes one request about every second, with a
  User-Agent naming the project, and backs off on 429 / server errors. Weekly runs only
  ask for records changed since the last run (`updated_since`); every 28 days it does a
  full re-pull, which drops deleted observations and ones no longer research grade.
  It saves nothing unless the run completes, and refuses a full pull that comes back
  with under 80% of the records already cached.
- **Cleaning** (`scripts/build_inat.py`): subspecies are counted under their species;
  `scripts/inat_name_map.json` merges iNaturalist's split taxa into Shepard & Guppy's
  lumped ones (e.g. *Celastrina echo* + *C. asheri* → *C. echo-asheri*); records
  identified only to genus, hybrids, and records with location accuracy worse than 5 km
  are left out. Observations whose location the observer obscured (blurred ~20 km) are
  kept and flagged: they count for the ecoregion and the 30/50 km circles, not 5/15 km.
- **Automation:** `.github/workflows/update-inat.yml` runs every Monday on GitHub
  Actions (fetch → build → photos/descriptions for new species) and commits the result
  if anything changed. Run it by hand from the repo's **Actions** tab → *Update
  iNaturalist data* → *Run workflow* (tick *full* for a complete re-pull). GitHub pauses
  scheduled workflows in repos with no activity for 60 days; if that happens, re-enable
  it on the same page.
- **By hand:** `python3 scripts/fetch_inat.py && python3 scripts/build_inat.py`
  (`--full` forces a complete re-pull).
- **Attribution:** observations belong to their observers; each iNat dot on the map
  links to its observation page.

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
- **Pipeline:** `scripts/build_ecoregions.py` (needs `pip install pyshp shapely`,
  shapely ≥ 2.1) writes:
  - `data/ecoregions.geojson` — outlines simplified to ~2 km (shared borders kept
    identical), for the map.
    The source builders tag each record with one of these (points just off the coast
    snap to the nearest ecoregion within ~5 km). If the outlines change, rebuild the
    sources.
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
- **Updates:** the weekly iNaturalist job runs this too, so species new to the data get
  a photo and description; existing entries are kept (it never removes species).
- **On the page:** a small photo next to each butterfly in the lists, and the photo +
  description at the top of each butterfly's detail view.

## How the app works

A location-first map for the public, combining a radius search with ecoregions.
(Each record's ecoregion is tagged at build time against the same simplified outlines the
page uses for "Your ecoregion", so the two always agree.)
(The earlier design options A and B and the radius map are in the git tag
`last-with-options`.)

- **Start:** one question, "Where is your backyard?" — search a town or postal code
  (OpenStreetMap's Nominatim geocoder, limited to Canada; light use only, searches run
  on submit, not per keystroke), **Use my location** (browser geolocation; needs
  localhost or https), or click the map.
- **Two levels of answer:** "Near you" (5 / 15 / 30 / 50 km) and "Your ecoregion"
  (found by point-in-polygon on `ecoregions.geojson`), each with species and sighting
  counts; click to switch. A short "What's an ecoregion?" explanation on demand.
- **Butterflies as photo cards**, filterable by name, "Flying in <this month>", sort, and
  year (the year menu appears only once there is more than one year of data). A card opens
  in place with the photo and description, a month-by-month chart, host (caterpillar) and
  nectar (adult) plants, and "Show where it's been seen" (dots on the map).
- Clicking the map reverse-geocodes a place name. The spot, distance and view are kept in
  the URL (e.g. `index.html#at=43.6535,-79.3839&r=30&view=region`).
- On narrow screens the map sits on top and the results scroll below it.

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

## Roadmap

- [ ] Add remaining Xerces regions to `plant-lists.json`.
- [ ] Plant/host data sources for non-Monarch species.
- [ ] Marker clustering for showing all observations at once.
- [ ] Deployment (undecided).
