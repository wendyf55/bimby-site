# BIMBY — Butterflies In My Backyard

A citizen-science map of Canada. Click a location to see which butterflies have been
observed within 15 km, then click a butterfly to see its host and nectar plants.

## Running locally

This site must be served over HTTP (not opened as a file), because it uses `fetch()`
to load the data files. From the repo root:

    python3 -m http.server 8000

Then open <http://localhost:8000>

## Repository structure

    index.html                     The whole app (map + interaction)
    option-a.html                  Design option A: browse by ecoregion
    option-b.html                  Design option B: ecoregion atlas (popup with species
                                   list, year charts, flight season, compare regions)
    option-c.html                  Design option C (placeholder for now)
    dev-switcher.js                Dev-mode option switcher (open any page with ?dev)
    species-info.js                Species photos + descriptions, shared by all pages
    data/                          (git-ignored)
      observations.json            Butterfly observations used by the app (generated)
      plant-lists.json             Host/nectar plant lists, one entry per region/source
      observations-782254.csv/     Raw iNaturalist export (kept for provenance)
      ecoregions.geojson           Simplified ecoregion outlines (generated)
      observation-ecoregions.json  Observation id -> ecoregion id (generated)
      ecozones.geojson             Ecozone outlines (generated; not currently used)
      species-info.json            Species descriptions + photos (generated)
      species-info-overrides.json  Optional hand fixes for the above
      raw/                         Ecoregion + ecozone shapefile zips from AAFC
    scripts/
      build_observations.py        Rebuilds observations.json from the raw CSV
      build_ecoregions.py          Builds the three ecoregion/ecozone files above
      build_species_info.py        Builds species-info.json (needs internet)

## Data sources

### Butterfly observations — iNaturalist

- **Source:** iNaturalist project *"2026 Butterflies in My Backyard (BIMBY)"*
  (project slug: `2026-butterflies-in-my-backyard-bimby-project`).
- **Export:** research-grade observations, exported 2026-09-15.
- **Contents:** 24,374 observations across 251 species; every record has coordinates.
- **Fields used:** `scientific_name`, `common_name`, `latitude`, `longitude`,
  `observed_on`, `id`.
- **Licensing:** individual observations carry their own licenses (e.g. CC-BY-NC);
  see the `license` column in the raw export. Attribute observers per iNaturalist terms.
- **Pipeline:** the raw export lives in `data/observations-782254.csv/`; running
  `scripts/build_observations.py` converts it to `data/observations.json`.

### Nectar & host plants — Xerces Society

- **Source:** Adamson, N. L., Fallon, C., & Vaughan, M. (2018).
  *Monarch Butterfly Nectar Plant Lists for Conservation Plantings.*
  The Xerces Society for Invertebrate Conservation. Publication 18-003_02.
- **URL:** <https://xerces.org/sites/default/files/publications/18-003_02_Monarch-Nectar-Plant-Lists-FS_web%20-%20Jessa%20Kay%20Cruz.pdf>
- **Scope so far:** the **Maritime Northwest** region (n.w. CA, w. OR, w. WA),
  25 species (3 are milkweeds = Monarch larval host plants). This is the closest
  Xerces region to British Columbia; note the Xerces regions are US-based, so
  BC is not literally covered.
- **Caveat:** these lists are **Monarch-specific**. Plant data for other species
  will need additional sources.

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

## Option B — ecoregion atlas

Modelled on the [Ontario Butterfly Atlas](https://www.ontarioinsects.org/atlas/).
Click an ecoregion to open a popup with:

- **Species list** — search; sort by most seen, rarest, A–Z or earliest in the year;
  first/last sighting dates. Click a species for its monthly sightings plus host &
  nectar plants.
- **Overview** — sightings by year and species by year (one bar per year; new years
  appear automatically as data is added), plus the top 5 species.
- **Flight season** — sightings per 10-day period with earliest / 10% / median / 90% /
  latest dates.
- **Compare regions** — ranking against the other ecoregions in the same ecozone.

In a species' detail view (Options A and B), **Show where it's been seen** recolours the
map by that species' sightings per ecoregion and zooms to where it has been recorded.
On the radius map (index.html) the same button plots every sighting of the species as a
dot (canvas layer, so thousands of points stay fast), filtered by the time period.

The sidebar colours the map by species or sightings, can map a single species, and
filters by year. The popup footer downloads the species list as CSV and copies a link;
the open region, tab and year are kept in the URL (e.g. `option-b.html#region=209&tab=season`).

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
