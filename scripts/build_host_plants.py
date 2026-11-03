"""
Build data/host-plants.json (plants caterpillars eat) from
data/hosts-deedes-clean.csv, which scripts/clean_hosts_deedes.py makes.

    {
      "built": "2026-11-03",
      "butterflies": [["Papilio zelicaon", "Anise Swallowtail"], ...],
      "plants": [["Heracleum maximum", "Cow parsnip", "perennial", "native"], ...],
      "rows": [[0, 12], ...],
      "noneKnown": [5, 9, ...]
    }

A row is [butterfly, plant], both positions in their lists. A plant's Latin name is
a genus ("Salix") when the list gives any species of that genus, and '' for
"Weedy pioneer plants". Status is from VASCAN ('' = unknown or a genus).
`noneKnown` lists butterflies for which the list says no host plants are known yet.

Usage (from the repo root):
    python3 scripts/build_host_plants.py
"""
import csv
import json
from datetime import date

SRC = "data/hosts-deedes-clean.csv"
OUT = "data/host-plants.json"


def index_of(lookup, key, values, value):
    """Adds `key` the first time it is seen; returns its position."""
    if key not in lookup:
        lookup[key] = len(values)
        values.append(value)
    return lookup[key]


def main():
    records = list(csv.DictReader(open(SRC, encoding="utf-8")))
    butterfly_index, butterflies = {}, []
    plant_index, plants = {}, []
    rows, none_known = [], []
    for r in records:
        b = index_of(butterfly_index, r["butterfly"], butterflies, [r["butterfly"], r["butterfly_common"]])
        if not r["plant_common"]:
            none_known.append(b)
            continue
        p = index_of(plant_index, (r["plant"], r["plant_common"]), plants,
                     [r["plant"], r["plant_common"], r["plant_type"], r["bc_status"]])
        rows.append([b, p])

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("{\n")
        f.write(f'  "built": "{date.today().isoformat()}",\n')
        for key, value in [("butterflies", butterflies), ("plants", plants)]:
            f.write(f'  "{key}": [\n' + ",\n".join("    " + json.dumps(v, ensure_ascii=False) for v in value) + "\n  ],\n")
        f.write(f'  "rows": {json.dumps(rows)},\n')
        f.write(f'  "noneKnown": {json.dumps(none_known)}\n}}\n')

    print(f"Wrote {OUT}: {len(rows)} butterfly-plant pairs, {len(butterflies)} butterflies "
          f"({len(none_known)} with no known host plants), {len(plants)} plants")


if __name__ == "__main__":
    main()
