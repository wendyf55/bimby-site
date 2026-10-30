"""
Build data/plant-visits.json (the flowers butterflies were seen on) from
data/plant-visits-clean.csv, which scripts/clean_plant_visits.py makes.

The page adds these up itself, so the file keeps one short row per record:

    {
      "built": "2026-10-30", "years": [2024, 2026],
      "butterflies": [["Ochlodes sylvanoides", "Woodland Skipper"], ...],
      "plants": [["Medicago sativa", "Alfalfa", "Fabaceae", "introduced"], ...],
      "fields": ["butterfly", "plant", "month", "person"],
      "rows": [[0, 12, 7, 3], ...]
    }

`butterfly` and `plant` index into their lists; `month` is 1-12; `person` is a
number that only tells observers apart (used for "seen by N people"). No names
or iNaturalist user ids are published. Plant status is from VASCAN ('' = unknown).

Usage (from the repo root):
    python3 scripts/build_plant_visits.py
"""
import csv
import json
from datetime import date

SRC = "data/plant-visits-clean.csv"
OUT = "data/plant-visits.json"


def index_of(lookup, key, values):
    """Adds `key` to `lookup` the first time it is seen; returns its position."""
    if key not in lookup:
        lookup[key] = len(lookup)
        values.append(None)
    return lookup[key]


def main():
    records = list(csv.DictReader(open(SRC, encoding="utf-8")))
    records.sort(key=lambda r: (r["butterfly"], r["plant"], r["date"]))

    butterfly_index, butterflies = {}, []
    plant_index, plants = {}, []
    person_index, people = {}, []
    rows = []
    for r in records:
        b = index_of(butterfly_index, r["butterfly"], butterflies)
        butterflies[b] = [r["butterfly"], r["butterfly_common"]]
        p = index_of(plant_index, r["plant"], plants)
        plants[p] = [r["plant"], r["plant_common"], r["plant_family"], r.get("bc_status", "")]
        person = index_of(person_index, r["user_id"], people)
        month = int(r["date"][5:7])
        rows.append([b, p, month, person])

    years = sorted(int(r["date"][:4]) for r in records)
    out = {
        "built": date.today().isoformat(),
        "years": [years[0], years[-1]],
        "butterflies": butterflies,
        "plants": plants,
        "fields": ["butterfly", "plant", "month", "person"],
        "rows": rows,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("{\n")
        for key in ["built", "years", "butterflies", "plants", "fields"]:
            f.write(f'  "{key}": {json.dumps(out[key], ensure_ascii=False)},\n')
        f.write('  "rows": [\n')
        f.write(",\n".join("    " + json.dumps(row) for row in rows))
        f.write("\n  ]\n}\n")

    print(f"Wrote {len(rows)} records to {OUT}: {len(butterflies)} butterflies, "
          f"{len(plants)} plants, {len(people)} observers")


if __name__ == "__main__":
    main()
