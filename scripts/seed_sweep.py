"""Seed sensitivity of every simulated column, and of the premium.

Answers "which published numbers are a draw from a seed distribution,
and which are not". Runs the REAL simulate() on the REAL scored frame at
several seeds and reports, per column, the national relative SD and the
max-min spread.

The one measurement that explains the rest is the ratio

    national relative SD / median per-district relative SD

`base` is drawn ONCE in simulate() and broadcast to every district, so
year j is the same state of the world everywhere and the per-district
Monte Carlo errors are near-perfectly correlated. A ratio near 1.00
means the national mean is as noisy as a single district - a 2,736
district portfolio buys NO error reduction. Independent errors would
give 1/sqrt(effective N) ~ 0.023.

Both calibrations are mandatory. main() calls calibrate_frequency AND
calibrate_spatial; the latter sets SPATIAL_SCALE, which drives the YEAR
view (tvar99_euler, and so capital and premium). Omitting it leaves the
module default of 1.0 - a 40x overstated spatial loading - and inflates
tvar99_euler ~9.7x while leaving tvar99_vine and el_total bit-identical
to the published run. A harness can look validated on the columns you
check and be wrong on the ones you care about.

With --write-json it also writes `data/seed_sensitivity.json`, which the
site injects so the methodology page can quote the standalone tail as a
measured RANGE instead of a point estimate. That file is committed and
CI does not regenerate it (a six-seed sweep is an hour of simulation),
exactly as `data/sector_validation.json` works.

    .venv/Scripts/python.exe scripts/seed_sweep.py 42 43 44
    .venv/Scripts/python.exe scripts/seed_sweep.py --write-json 42 43 44
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import build_model as bm

ARGS = [a for a in sys.argv[1:] if a != "--write-json"]
WRITE_JSON = "--write-json" in sys.argv
SEEDS = [int(a) for a in ARGS] or [42, 43]
COLS = ["el_total", "el_year", "tvar99_euler", "var995_vine",
        "tvar99_indep", "tvar99_vine", "tvar99_gauss"]


def scored_frame():
    """Re-derive the scored districts, as analytic_el_check.py does."""
    g = bm.load_districts()
    bng = g.to_crs(27700)
    pts = bng.geometry.representative_point()
    targets = np.column_stack([pts.x.values, pts.y.values])
    (g["sub_score"], g["geol"], g["sup_frac"],
     g["sup_geol"]) = bm.subsidence_score(bng)
    g["wx_score"], wx = bm.weather_from_metoffice(targets)
    g["wind_ms"], g["wdr_idx"] = wx["wind"], wx["wdr"]
    g["rain10_days"], g["precip_mm"] = wx["rain10"], wx["precip"]
    g["gust_rp50"] = wx["gust_rp50"]
    (g["fl_score"], g["f_high"], g["f_low"],
     g["sw_high"], g["sw_low"]) = bm.flood_from_agencies(g["name"].values)
    g["gw_score"], g["gw_frac"] = bm.groundwater_from_ea(g["name"].values)
    g["country"] = bm.load_country(g["name"].values)
    g["er_score"], er = bm.erosion_from_ncerm(g["name"].values)
    for c, v in er.items():
        g[c] = v
    g["er_frac"] = g["er_smp105"]
    g["households"] = bm.load_households(g["name"].values)
    g["sw_sev"], g["sw_depth_m"] = bm.sw_depth_severity(
        g["name"].values, g["sw_high"].values, g["sw_low"].values,
        g["households"].values)
    g["th_rate"] = bm.theft_from_police(g["name"].values,
                                        g["households"].values)
    g["frost_days"] = bm.frost_from_metoffice(targets)
    fmean = np.average(g["frost_days"], weights=g["households"])
    g["eow_rate"] = bm.ABI_TARGET_FREQ["eow"] * (
        (1.0 - bm.EOW_FREEZE_SHARE)
        + bm.EOW_FREEZE_SHARE * g["frost_days"] / fmean)
    fire_raw = bm.fires_from_mhclg(g["name"].values, g["households"].values)
    g["fire_rate"] = bm.ABI_TARGET_FREQ["fire"] * fire_raw / np.average(
        fire_raw, weights=g["households"])
    cs = bm.children_from_census(g["name"].values, g["households"].values)
    g["ad_rate"] = bm.ABI_TARGET_FREQ["ad"] * (
        (1.0 - bm.AD_CHILD_SHARE) + bm.AD_CHILD_SHARE * cs / np.average(
            cs, weights=g["households"]))
    return g


def main():
    g = scored_frame()
    bm.check_scored_columns(g)
    bm.calibrate_frequency(g)
    bm.calibrate_spatial(g)          # REQUIRED - see the module docstring
    w = g["households"].values.astype(float)
    n_eff = w.sum() ** 2 / (w ** 2).sum()

    runs = {}
    for s in SEEDS:
        bm.RNG_SEED = s
        t0 = time.time()
        sim, _ = bm.simulate(g)
        runs[s] = {c: np.asarray(sim[c], dtype=float)
                   for c in COLS if c in sim}
        runs[s]["premium"] = runs[s]["el_total"] + 0.06 * np.maximum(
            runs[s]["tvar99_euler"] - runs[s]["el_total"], 0.0)
        print(f"  seed {s} in {time.time() - t0:.0f}s", flush=True)

    print(f"\ndistricts {len(w)}   effective N {n_eff:.0f}   "
          f"seeds {SEEDS}")
    print(f"\n{'column':16}{'rel SD':>9}{'max-min':>9}{'nat/dist':>10}"
          f"  per-seed national means")
    for c in COLS + ["premium"]:
        if c not in runs[SEEDS[0]]:
            continue
        M = np.stack([runs[s][c] for s in SEEDS])
        nat = np.array([np.average(M[i], weights=w)
                        for i in range(len(SEEDS))])
        s_nat = nat.std(ddof=1) / nat.mean()
        s_dis = float(np.median(M.std(axis=0, ddof=1)
                                / np.maximum(M.mean(axis=0), 1e-12)))
        ratio = s_nat / s_dis if s_dis > 1e-12 else float("nan")
        vals = " ".join(f"{v:,.0f}" if v > 999 else f"{v:,.3f}" for v in nat)
        print(f"{c:16}{100 * s_nat:8.2f}%"
              f"{100 * (nat.max() - nat.min()) / nat.mean():8.2f}%"
              f"{ratio:10.3f}  {vals}")
    print(f"\nratio ~1.00 = errors comonotone across districts, no averaging;"
          f"\nindependent errors would give {1 / np.sqrt(n_eff):.3f}.")

    if not WRITE_JSON:
        return
    if len(SEEDS) < 3:
        sys.exit("--write-json needs at least 3 seeds to quote a range")

    # build_site injects these. The site quotes the standalone tail as a
    # range because its error is comonotone across districts (see above);
    # the allocated share and the premium are quoted as points because
    # theirs is not. Both claims come from the same numbers.
    def summary(col, weighted=True):
        M = np.stack([runs[s][col] for s in SEEDS])
        nat = np.array([np.average(M[i], weights=w) if weighted
                        else M[i].mean() for i in range(len(SEEDS))])
        s_dis = float(np.median(M.std(axis=0, ddof=1)
                                / np.maximum(M.mean(axis=0), 1e-12)))
        s_nat = float(nat.std(ddof=1) / nat.mean())
        return {
            "per_seed": [round(float(v), 4) for v in nat],
            "min": float(nat.min()), "max": float(nat.max()),
            "mean": float(nat.mean()),
            "rel_sd_pct": round(100 * s_nat, 4),
            "spread_pct": round(100 * (nat.max() - nat.min()) / nat.mean(), 4),
            # >0.5 means the national mean is as noisy as one district
            "noise_ratio": round(s_nat / s_dis, 4) if s_dis > 1e-12 else None,
        }

    # the site's two figures use a PLAIN mean over districts, as
    # build_site.py does - not the household-weighted one
    stand = summary("tvar99_vine", weighted=False)
    port = summary("tvar99_euler", weighted=False)
    div = [100 * (1 - p / s)
           for s, p in zip(stand["per_seed"], port["per_seed"])]
    out = {
        "generated_by": "scripts/seed_sweep.py --write-json",
        "n_sim": bm.N_SIM,
        "seeds": SEEDS,
        "districts": int(len(w)),
        "effective_n": round(float(n_eff), 1),
        "independent_ratio": round(float(1 / np.sqrt(n_eff)), 4),
        "standalone_tvar99": stand,
        "port_tvar99": port,
        "premium": summary("premium"),
        "el_total": summary("el_total"),
        "diversification_pct": {"min": min(div), "max": max(div),
                                "per_seed": [round(d, 4) for d in div]},
    }
    path = os.path.join(bm.DATA, "seed_sensitivity.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
