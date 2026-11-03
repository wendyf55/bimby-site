"""
Clean the B.C. host plant list by Stephen Deedes and Sally Hocking
(data/hosts-Deedes.xlsx, from https://butterflies.deedesie.com/b-c-host-plants/)
into data/hosts-deedes-clean.csv, one row per butterfly and the plant its
caterpillars eat.

Steps:
  1. Tidy spacing and match butterfly names to the names used on the site, using
     scripts/deedes_name_map.json (older names like "Speyeria" -> "Argynnis").
  2. Fix plant name typos and turn "Salix spp" and similar into the genus ("Salix").
  3. Pick one common name per plant: the one used most often in the list, unless
     scripts/deedes_name_map.json gives a better one.
  4. Add each plant's status in BC from VASCAN's archive (scripts/vascan.py): the
     full name first ("Urtica dioica subsp. gracilis"), then the species.
     Genus entries get no status.
  5. Butterflies whose only entry is "unknown" are kept with an empty plant, so the
     page can say no host plants are known yet.
The list's "Place" and "AlternatePlantName" columns are not used.

Usage:
    python3 scripts/clean_hosts_deedes.py
"""
import csv
import json
import re
from collections import Counter

import openpyxl

from clean_plant_visits import load_butterfly_names
from vascan import Vascan

SRC = "data/hosts-Deedes.xlsx"
OUT = "data/hosts-deedes-clean.csv"
NAME_MAP = "scripts/deedes_name_map.json"

COLUMNS = ["butterfly", "butterfly_common", "plant", "plant_common", "plant_type", "bc_status",
           "list_butterfly", "list_plant"]


def tidy(value):
    """Collapses repeated spaces and trims; empty cells become ''."""
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""


def read_list():
    """Rows of the spreadsheet as dicts, using the header row (the 2nd row)."""
    sheet = openpyxl.load_workbook(SRC, read_only=True).worksheets[0]
    rows = [[tidy(cell) for cell in row] for row in sheet.iter_rows(values_only=True)]
    header = rows[1]
    return [dict(zip(header, row)) for row in rows[2:] if any(row)]


def plant_name(row, fixes):
    """Corrected Latin name: 'Salix spp' -> 'Salix', typos fixed. '' if unknown."""
    sci, common = row["PlantLatinName"], row["PlantEnglishName"]
    sci = fixes.get(f"{sci}|{common}", fixes.get(sci, sci))
    if sci.lower() == "unknown" or common.lower() == "weedy pioneer spp":
        return "" if sci.lower() == "unknown" else "weedy pioneer"
    sci = re.sub(r"\s+(spp|sps|sp)\.?$", "", sci)        # genus: "Salix spp" -> "Salix"
    sci = re.sub(r"\s+ssp\.?\s+", " subsp. ", sci)        # "ssp" -> "subsp."
    return sci


def clean_common(name):
    """'Willow spp' -> 'Willow'; 'Pacific Water Parsley' -> 'Pacific water parsley'
    (first letter capital only, like the plant names on the rest of the site)."""
    name = re.sub(r"\s+(spp|sps)\.?$", "", name).strip()
    return name[:1].upper() + name[1:].lower()


def plant_type(text):
    """'shrub/tree' -> 'shrub or tree'; 'unknown' -> ''."""
    return "" if text.lower() in ("", "unknown") else text.replace("/", " or ")


def species_part(sci):
    """'Urtica dioica subsp. gracilis' -> 'Urtica dioica'; '' for genus or family names."""
    words = sci.split()
    return " ".join(words[:2]) if len(words) >= 2 else ""


def main():
    names = json.load(open(NAME_MAP))
    butterfly_map, plant_fixes, common_fixes = names["butterflies"], names["plants"], names["plant_common"]
    _, site_common = load_butterfly_names()
    rows = read_list()

    # One common name and type per plant, the most used in the list
    commons, types = {}, {}
    for row in rows:
        sci = plant_name(row, plant_fixes)
        if sci and sci != "weedy pioneer":
            commons.setdefault(sci, Counter())[clean_common(row["PlantEnglishName"])] += 1
            if plant_type(row["PlantCategory"]):
                types.setdefault(sci, Counter())[plant_type(row["PlantCategory"])] += 1
    plant_common = {sci: common_fixes.get(sci, c.most_common(1)[0][0]) for sci, c in commons.items()}
    plant_common["weedy pioneer"] = common_fixes[""]
    plant_types = {sci: c.most_common(1)[0][0] for sci, c in types.items()}

    #status in bc -  the full name first
    # then the species. Genus and group entries get none.
    vascan = Vascan()
    status = {sci: vascan.bc_status(sci) or vascan.bc_status(species_part(sci))
              for sci in plant_common if species_part(sci)}

    out, not_on_site, skipped = {}, Counter(), Counter()
    for row in rows:
        listed = row["ButterflyLatinName"]
        mapped = butterfly_map.get(listed, " ".join(listed.split()[:2]))
        if mapped is None:
            skipped[listed] += 1
            continue
        plant = plant_name(row, plant_fixes)
        for butterfly in (mapped if isinstance(mapped, list) else [mapped]):
            if butterfly not in site_common:
                not_on_site[f"{butterfly} ({row['ButterflyEnglishName']})"] += 1
            key = (butterfly, plant)
            if key in out:
                continue   # the same pair listed twice (e.g. two subspecies)
            out[key] = {
                "butterfly": butterfly,
                "butterfly_common": site_common.get(butterfly) or row["ButterflyEnglishName"],
                "plant": "" if plant == "weedy pioneer" else plant,
                "plant_common": plant_common.get(plant, ""),
                "plant_type": plant_types.get(plant, ""),
                "bc_status": status.get(plant, ""),
                "list_butterfly": listed,
                "list_plant": row["PlantLatinName"],
            }

    # A butterfly with real plants doesn't also need an "unknown" row
    known = {b for (b, p), r in out.items() if r["plant_common"]}
    rows_out = [r for (b, p), r in out.items() if r["plant_common"] or b not in known]
    rows_out.sort(key=lambda r: (r["butterfly"], r["plant_common"]))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows_out)

    # Summary
    with_plants = {r["butterfly"] for r in rows_out if r["plant_common"]}
    unknown = sorted({r["butterfly"] for r in rows_out} - with_plants)
    plants = {r["plant"] or r["plant_common"] for r in rows_out if r["plant_common"]}
    print(f"\nRead {len(rows)} rows, wrote {len(rows_out)} to {OUT}")
    print(f"{len(with_plants)} butterflies with host plants, {len(unknown)} with none known, "
          f"{len(plants)} plants ({sum(1 for p in plants if not species_part(p))} genus or group entries)")
    counts = Counter(status.get(p, "") or "no status" for p in plants if species_part(p))
    print("Plant species by status in BC:", ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    unconfirmed = names.get("unconfirmed", {})
    if skipped:
        print("Left out, no confirmed match yet:", ", ".join(n for n in skipped if n in unconfirmed))
        print("Left out, not recorded in BC on the site:", ", ".join(n for n in skipped if n not in unconfirmed))
    if not_on_site:
        print("Butterflies not in the site's species list (kept, using the list's common name):")
        for name in sorted(not_on_site):
            print("  ", name)


if __name__ == "__main__":
    main()
