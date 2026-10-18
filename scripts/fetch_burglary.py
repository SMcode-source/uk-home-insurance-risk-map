"""Count burglaries per postcode district from the police.uk bulk archive.

Source: police.uk open data archive (Single Online Home / Home Office),
Open Government Licence:

    https://data.police.uk/data/archive/latest.zip
    -> redirects to policeuk-data.s3.amazonaws.com/archive/<YYYY-MM>.zip

The archive holds 36 months of street-level crime for England, Wales,
Northern Ireland and British Transport Police, one CSV per force per
month (`<month>/<month>-<force>-street.csv`). Scotland is NOT covered
(Police Scotland publishes no incident-level data); the model applies a
country-mask fallback downstream - see scores_real.py.

Each row is one recorded crime with a Crime type ("Burglary" here covers
both residential and commercial premises) and an anonymised snap-point
Longitude/Latitude: the true location is moved to the nearest point on a
master list of ~750k street-level anchors, each covering >= 8 postal
addresses. That displacement is a few hundred metres at most - noise at
postcode-district scale, which is why the join is done on coordinates
against the district polygons rather than via the row's LSOA code (the
archive's LSOA vintage has drifted across census editions; polygons
haven't).

Rows are spatially joined to the same district polygons the model scores
on (build_model.load_districts). Rows with no coordinates, or whose snap
point falls outside every district polygon (Northern Ireland, offshore),
are counted and reported but excluded.

The machine this runs on sleeps mid-run, so the scan checkpoints to
data/cache/burglary_checkpoint.json every 100 member files and resumes
from there; a sleep costs at most 100 files, not the whole 1,562.
Delete the checkpoint to force a full rescan (e.g. after replacing the
archive with a newer month).

Output: data/burglary.csv, one row per GB postcode district:
    name        district (e.g. YO8)
    burglaries  burglary count over the archive window
    months      window length in months (36), so annual rate =
                burglaries / months * 12

Scottish districts appear with burglaries=0 - absence of data, not
absence of burglary. Do not read this file without the country mask.

Usage:
    python -u scripts/fetch_burglary.py
"""

import csv
import json
import os
import sys
import time
import zipfile

import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_model import load_districts  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
CACHE = os.path.join(DATA, "cache")
ARCHIVE = os.path.join(CACHE, "police_archive_2026-06.zip")
CHECKPOINT = os.path.join(CACHE, "burglary_checkpoint.json")
OUT = os.path.join(DATA, "burglary.csv")

CHECKPOINT_EVERY = 100  # member files between checkpoint writes


def save_checkpoint(state):
    tmp = CHECKPOINT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, CHECKPOINT)


def main():
    districts = load_districts()
    tree = shapely.STRtree(districts.geometry.values)
    names = districts["name"].values

    state = {"processed": [], "counts": {}, "unlocated": 0, "outside": 0}
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as f:
            state = json.load(f)
        print(f"resuming: {len(state['processed'])} files already done")
    done = set(state["processed"])
    counts = state["counts"]

    z = zipfile.ZipFile(ARCHIVE)
    street = sorted(m for m in z.namelist() if m.endswith("-street.csv"))
    months = sorted({m.split("/")[0] for m in street})
    print(f"{len(street)} street files, {len(months)} months "
          f"{months[0]}..{months[-1]}")

    t0 = time.time()
    n_done = 0
    for member in street:
        if member in done:
            continue
        with z.open(member) as f:
            try:
                df = pd.read_csv(f, usecols=["Longitude", "Latitude",
                                             "Crime type"])
            except (pd.errors.EmptyDataError, ValueError) as e:
                print(f"  {member}: unreadable ({e}), counted as empty")
                df = pd.DataFrame(columns=["Longitude", "Latitude",
                                           "Crime type"])
        b = df[df["Crime type"] == "Burglary"]
        loc = b.dropna(subset=["Longitude", "Latitude"])
        state["unlocated"] += int(len(b) - len(loc))

        if len(loc):
            pts = shapely.points(loc["Longitude"].values,
                                 loc["Latitude"].values)
            hit = tree.query(pts, predicate="intersects")
            # A snap point on a shared boundary can hit two districts;
            # keep the lowest geometry index so reruns are deterministic.
            if hit.shape[1]:
                order = np.lexsort((hit[1], hit[0]))
                pi, gi = hit[0][order], hit[1][order]
                first = np.concatenate(([True], pi[1:] != pi[:-1]))
                for g in gi[first]:
                    nm = names[g]
                    counts[nm] = counts.get(nm, 0) + 1
                n_matched = int(first.sum())
            else:
                n_matched = 0
            state["outside"] += int(len(loc) - n_matched)

        state["processed"].append(member)
        n_done += 1
        if n_done % CHECKPOINT_EVERY == 0:
            save_checkpoint(state)
            rate = n_done / (time.time() - t0)
            left = len(street) - len(state["processed"])
            print(f"  {len(state['processed'])}/{len(street)} files, "
                  f"{sum(counts.values()):,} burglaries placed, "
                  f"~{left / rate / 60:.0f} min left", flush=True)

    save_checkpoint(state)

    total = sum(counts.values())
    print(f"\nplaced {total:,} burglaries in {len(counts)} districts; "
          f"{state['unlocated']:,} rows had no coordinates, "
          f"{state['outside']:,} fell outside every polygon (NI etc.)")

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "burglaries", "months"])
        for nm in sorted(set(names)):
            w.writerow([nm, counts.get(nm, 0), len(months)])
    print(f"wrote {OUT}")

    top = sorted(counts.items(), key=lambda kv: -kv[1])[:5]
    print("busiest districts:", ", ".join(f"{n} {c:,}" for n, c in top))


if __name__ == "__main__":
    main()
