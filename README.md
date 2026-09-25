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
    option-b.html, option-c.html   Design options B, C (placeholders for now)
    dev-switcher.js                Dev-mode option switcher (open any page with ?dev)
    data/                          (git-ignored)
      observations.json            Butterfly observations used by the app (generated)
      plant-lists.json             Host/nectar plant lists, one entry per region/source
      observations-782254.csv/     Raw iNaturalist export (kept for provenance)
      ecoregions.geojson           Simplified ecoregion outlines (generated)
      observation-ecoregions.json  Observation id -> ecoregion id (generated)
      raw/                         Ecoregion + ecozone shapefile zips from AAFC
    scripts/
      build_observations.py        Rebuilds observations.json from the raw CSV
      build_ecoregions.py          Builds the two ecoregion files above

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

### Ecoregions — National Ecological Framework for Canada (used by option-a.html)

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
