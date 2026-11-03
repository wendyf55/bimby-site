"""
native / non-native Plant status in British Columbia from VASCAN
read from its Darwin Core Archive (no internet needed once downloaded).

downloaded the archive once into data/raw/ (about 3 MB, CC0):
    curl -L -o data/raw/vascan-dwca.zip "https://data.canadensys.net/ipt/archive.do?r=vascan&v=37.17"
    (this is cited in app.js)

Statuses returned for BC (the same words the VASCAN website uses):
  native      present and native
  introduced  present and introduced
  ephemeral   introduced, but only shows up now and then
  excluded    reported from BC in the past, but VASCAN rejects the report
  doubtful    VASCAN isn't sure it occurs in BC
  extirpated  no longer found in BC
  absent      VASCAN has a distribution for the plant and BC isn't in it
  mixed       some varieties/subspecies are native in BC and others introduced
website shows no tag for these
  ''          unknown: VASCAN doesn't know the name, or says nothing about where it grows
"""
import csv
import io
import re
import zipfile
from collections import defaultdict

ARCHIVE = "data/raw/vascan-dwca.zip"

STATUS = {
    ("present", "native"): "native",
    ("present", "introduced"): "introduced",
    ("irregular", "introduced"): "ephemeral",
    ("excluded", ""): "excluded",
    ("doubtful", ""): "doubtful",
    ("absent", ""): "extirpated",
}
# When combining varieties, the first status found in this order wins
ORDER = ["native", "introduced", "ephemeral", "extirpated", "doubtful", "excluded", "absent"]
BC = "ISO3166-2:CA-BC"


def read(archive, name):
    """Rows of one tab-separated file inside the archive, as dicts."""
    with zipfile.ZipFile(archive) as z:
        text = io.TextIOWrapper(z.open(name), encoding="utf-8")
        yield from csv.DictReader(text, delimiter="\t", quoting=csv.QUOTE_NONE)


def canonical(row):
    """'Acer glabrum var. douglasii' from a taxon row (no author)."""
    name = f"{row['genus']} {row['specificEpithet']}".strip()
    if row["infraspecificEpithet"]:
        marker = {"variety": "var.", "subspecies": "subsp."}.get(row["taxonRank"], row["taxonRank"])
        name += f" {marker} {row['infraspecificEpithet']}"
    return name


class Vascan:
    def __init__(self, archive=ARCHIVE):
        self.taxa, self.by_name, self.children = {}, defaultdict(list), defaultdict(list)
        for row in read(archive, "taxon.txt"):
            if row["taxonRank"] not in ("species", "subspecies", "variety"):
                continue
            self.taxa[row["id"]] = row
            self.by_name[canonical(row)].append(row["id"])
            if row["taxonomicStatus"] == "accepted" and row["parentNameUsageID"]:
                self.children[row["parentNameUsageID"]].append(row["id"])
        self.has_distribution, self.in_bc = set(), {}
        for row in read(archive, "distribution.txt"):
            self.has_distribution.add(row["id"])
            if row["locationID"] == BC:
                self.in_bc[row["id"]] = STATUS.get((row["occurrenceStatus"], row["establishmentMeans"]), "")

    def accepted_id(self, name):
        """vascan id of the accepted taxon for a name, following synonyms."""
        ids = self.by_name.get(re.sub(r"\s+", " ", name.strip()), [])
        accepted = [i for i in ids if self.taxa[i]["taxonomicStatus"] == "accepted"]
        if accepted:
            return accepted[0] if len(accepted) == 1 else None
        targets = {self.taxa[i]["acceptedNameUsageID"] for i in ids}
        return targets.pop() if len(targets) == 1 else None

    def status_of_taxon(self, taxon_id):
        if taxon_id in self.in_bc:
            return self.in_bc[taxon_id]
        if taxon_id in self.has_distribution:
            return "absent"
        found = [self.status_of_taxon(child) for child in self.children[taxon_id]]
        has_native = any(s in ("native", "mixed") for s in found)
        has_introduced = any(s in ("introduced", "ephemeral", "mixed") for s in found)
        if has_native and has_introduced:
            return "mixed"
        for status in ORDER:
            if status in found:
                return status
        return ""

    def bc_status(self, name):
        """Status in BC for a Latin name ('' if unknown)."""
        taxon_id = self.accepted_id(name)
        return self.status_of_taxon(taxon_id) if taxon_id else ""


if __name__ == "__main__":
    # Quick look: python3 scripts/vascan.py "Quercus garryana" "Heracleum maximum"
    import sys
    v = Vascan()
    for name in sys.argv[1:]:
        print(f"{name}: {v.bc_status(name) or '(unknown)'}")
