"""Guards on the GitHub Actions workflows themselves.

The model's two grains are built on runners, and a runner starts with
nothing: no datum grid, no geology, no postcode centroids. The scripts
guard their own inputs (fetch_onspd.py refuses to run without the OSTN15
grid rather than let pyproj fall back to a Helmert shift), so a job that
forgets a setup step fails loudly - but only when that job actually
runs, and the fetch jobs of sector-model.yml run only on a full fetch.
The flood job published on 2026-09-06 had never run: the first full
fetch (run 34056186038) died in five seconds in two jobs, on the grid.

These tests read the workflow files as data and assert the ordering
that the scripts require, so the mistake is caught by `tests.yml` on
the push that makes it, not by the next full fetch weeks later.
"""
import glob
import os
import re

import pytest
import yaml

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")

OSTN15_STEP = "Install the OSTN15 datum grid"

# Workflows that produce COMMITTED model inputs or outputs. Anything they
# rasterise or sample has to see the same transform the build does; the
# measurement-only workflows are deliberately out of scope.
BUILD_WORKFLOWS = ["sector-model.yml", "rebuild.yml", "sw-refetch.yml",
                   "rs-depth.yml"]

# Which scripts need the grid is DERIVED, not listed. The hand-written
# list missed fetch_sw_depth.py for six weeks, and the district depth
# bands were rasterised against polygons 2-7 m from the model's own -
# up to 0.54 of a 13 m pixel (HANDOFF 2026-09-12). A list only guards
# what someone remembered to put in it.
TRANSFORM_CALL = re.compile(r"to_crs\(\s*(?:27700|[\"']EPSG:27700[\"'])"
                            r"|from_epsg\(\s*27700\s*\)")


def _transforming_scripts():
    out = set()
    for path in glob.glob(os.path.join(ROOT, "scripts", "*.py")):
        with open(path, encoding="utf-8") as fh:
            if TRANSFORM_CALL.search(fh.read()):
                out.add(os.path.basename(path))
    assert "build_model.py" in out, "the detector stopped detecting"
    return out


NEEDS_OSTN15 = sorted(_transforming_scripts())


def _load(name):
    with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _steps_running(job, script):
    for i, step in enumerate(job.get("steps", [])):
        run = step.get("run") or ""
        if script in run:
            yield i, step


@pytest.mark.parametrize("workflow", BUILD_WORKFLOWS)
def test_every_job_installs_ostn15_before_it_transforms(workflow):
    wf = _load(workflow)
    for job_name, job in wf["jobs"].items():
        steps = job.get("steps", [])
        grid_at = [i for i, s in enumerate(steps) if s.get("name") == OSTN15_STEP]
        for script in NEEDS_OSTN15:
            for i, step in _steps_running(job, script):
                assert grid_at and grid_at[0] < i, (
                    f"{workflow} job '{job_name}' runs {script} at step {i} "
                    f"without '{OSTN15_STEP}' before it")


def test_rebuild_ostn15_step_is_optional_for_measurement_only():
    """rebuild.yml's grid step is gated on an input so the Helmert
    approximation can be built for comparison; that gate must default
    to on, or a plain dispatch would publish the less accurate transform."""
    wf = _load("rebuild.yml")
    inputs = wf[True]["workflow_dispatch"]["inputs"] if True in wf else \
        wf["on"]["workflow_dispatch"]["inputs"]
    assert inputs["ostn15"]["default"] is True


def test_sector_model_commits_every_regenerated_input():
    """The model job's commit step must list every file a fetch job or
    the model job itself regenerates, or a full fetch silently builds
    from new inputs and commits an output nobody can reproduce."""
    wf = _load("sector-model.yml")
    model = wf["jobs"]["model"]
    commit = next(s for s in model["steps"]
                  if "git add" in (s.get("run") or ""))["run"]
    for f in ("data/erosion.csv", "data/flood_fractions.csv",
              "data/sw_fractions.csv", "data/sw_depth.csv",
              "data/subsidence_postcodes.csv",
              "data/districts_risk.geojson", "data/year_analysis.json"):
        assert f in commit, f"{f} is regenerated but not committed"
    # and the continuation lines are real continuations, not a literal \n
    assert "\\n" not in commit


def _sw_tables_produced(job):
    """The tables an aggregation step of `job` writes, by the script and
    flags it runs. A --flags step writes a gitignored intermediate and
    produces nothing committable."""
    produced = set()
    for step in job.get("steps", []):
        run = step.get("run") or ""
        for script, stem in (("fetch_sw_postcodes.py", "sw_fractions"),
                             ("fetch_sw_depth_postcodes.py", "sw_depth")):
            if script not in run or "--flags" in run:
                continue
            produced.add(f"{stem}_cc.csv" if "--climate" in run
                         else f"{stem}.csv")
    return produced


def test_sw_refetch_commits_and_pairs_every_table_it_fetches():
    """The depth bands and the envelope they are conditioned on are two
    samplings of the same postcode centroids. Fetching one without the
    other is what makes the pair unreadable, so every table a job
    produces must be committed by the same run - and the guard first.

    Both products moved to postcode share (frequency 2026-09-06, the
    depth conditional 2026-09-20), so the area-share pair this workflow
    used to refetch - fetch_sw_depth.py and fetch_surface_water.py --out
    sw_fractions_area - is superseded and must not come back here: a
    depth table written by fetch_sw_depth.py would put the model back on
    the area basis while every shape guard passed."""
    wf = _load("sw-refetch.yml")
    produced = set()
    for job in wf["jobs"].values():
        produced |= _sw_tables_produced(job)
        for step in job.get("steps", []):
            run = step.get("run") or ""
            assert "fetch_sw_depth.py" not in run, (
                "sw-refetch runs the superseded AREA-share depth fetch; "
                "the model reads sw_depth.csv on the postcode basis")
            assert "sw_fractions_area" not in run, (
                "sw-refetch writes an area envelope no longer read by "
                "scores_real.sw_depth_severity")
    assert produced == {"sw_fractions.csv", "sw_fractions_cc.csv",
                        "sw_depth.csv", "sw_depth_cc.csv"}, \
        f"a depth table and its envelope must be refetched together: {produced}"

    # A postcode's envelope is whichever service paints it, and the three
    # overlap at the border, so a single-region refetch cannot repair a
    # border unit whichever way it merges - both ways were measured wrong
    # on 2026-09-12. The present-day fractions need all three.
    for job in wf["jobs"].values():
        if "sw_fractions.csv" not in _sw_tables_produced(job):
            continue
        fetched = set()
        for step in job.get("steps", []):
            run = step.get("run") or ""
            if "fetch_sw_postcodes.py --flags" not in run:
                continue
            fetched |= {r for r in ("england", "wales", "scotland") if r in run}
        assert fetched == {"england", "wales", "scotland"}, (
            f"sw-refetch fetches only {sorted(fetched)} into the present-day "
            f"fractions; a missing region reads downstream as no water")

    steps = wf["jobs"]["collect"]["steps"]
    commit = next(s for s in steps if "git add" in (s.get("run") or ""))
    for f in produced:
        assert f"data/{f}" in commit["run"], f"{f} is fetched but not committed"
    assert "\\n" not in commit["run"]

    guard = next(i for i, s in enumerate(steps)
                 if "pytest" in (s.get("run") or ""))
    assert guard < steps.index(commit), "the guard must run before the commit"

    # tests/test_inputs.py checks the SHAPE of a table (shares, nesting,
    # a ceiling); it cannot know how big a refetch should be, and it
    # passed on the doubled file of 2026-09-12. The size check compares
    # each table against the one it replaces, so it has to see all four.
    size = next((i for i, s in enumerate(steps)
                 if "check_refetch_delta.py" in (s.get("run") or "")), None)
    assert size is not None, (
        "collect must run scripts/check_refetch_delta.py - the shape guard "
        "passes on a table that is twice the truth")
    assert size < steps.index(commit), (
        "the size check must run before the commit, not after it")
    for f in produced:
        assert f"data/{f}" in steps[size]["run"], (
            f"{f} is fetched but not size-checked against its predecessor")


@pytest.mark.parametrize("workflow", ["sw-refetch.yml", "sector-model.yml"])
def test_depth_is_sampled_in_the_job_that_fetched_its_envelope(workflow):
    """fetch_sw_depth_postcodes.py's aggregation reads two files the
    frequency stage produces: data/sw_flags_england[_cc].csv, the
    per-postcode envelope it enforces against, and the sw_fractions
    table it clips a shrunken thin unit to. The flags are gitignored
    (~20 MB) and are never uploaded as an artifact, so a depth job
    running in parallel would find neither on a fresh runner and fall
    back to the committed pair - conditioning a new depth measurement on
    an old envelope, with every shape guard passing. The two stages must
    therefore share a job, in that order."""
    wf = _load(workflow)
    seen = False
    for job_name, job in wf["jobs"].items():
        flags_at = [i for i, s in enumerate(job.get("steps", []))
                    if "fetch_sw_postcodes.py --flags" in (s.get("run") or "")]
        for i, _ in _steps_running(job, "fetch_sw_depth_postcodes.py"):
            seen = True
            assert flags_at and flags_at[0] < i, (
                f"{workflow} job '{job_name}' samples depth at step {i} "
                f"without fetching the envelope flags before it")
    assert seen, f"{workflow} no longer samples depth at all"


# Scripts that reach build_model.load_districts(), which since 2026-09-25
# refuses to run without the OSTN15 grid. Derived, like NEEDS_OSTN15: a
# script that calls load_districts or drives build_model.main() directly.
_LOADS = re.compile(r"load_districts\(|\bbm\.main\(\)|build_model\.main\(\)")


def _loading_scripts():
    out = set()
    for path in glob.glob(os.path.join(ROOT, "scripts", "*.py")):
        with open(path, encoding="utf-8") as fh:
            if _LOADS.search(fh.read()):
                out.add(os.path.basename(path))
    assert {"build_model.py", "price_smd_curve.py"} <= out, \
        "the detector stopped detecting"
    return sorted(out)


def _allows_helmert(wf, job):
    return any("UKRISK_ALLOW_HELMERT" in (scope.get("env") or {})
               for scope in (wf, job))


@pytest.mark.parametrize("workflow", sorted(
    os.path.basename(p) for p in glob.glob(os.path.join(WORKFLOWS, "*.yml"))))
def test_every_model_run_has_the_grid_or_says_it_does_not(workflow):
    """The measurement workflows were out of scope of the test above, and
    six of them priced variants on the Helmert fallback while the
    published model used OSTN15 - the variant and baseline shared a
    datum, so the deltas mostly held, but neither baseline was the
    published model. Now the model itself refuses (require_ostn15), so a
    workflow without the step would fail at runtime; this catches it on
    the push instead. The only way round is to say so in `env`."""
    wf = _load(workflow)
    for job_name, job in wf["jobs"].items():
        if _allows_helmert(wf, job):
            continue
        steps = job.get("steps", [])
        grid_at = [i for i, s in enumerate(steps) if s.get("name") == OSTN15_STEP]
        for script in _loading_scripts():
            # whole name only: check_pet_sensitivity.py is not sensitivity.py
            pat = re.compile(r"scripts/" + re.escape(script) + r"\b")
            for i, s in enumerate(steps):
                if not pat.search(s.get("run") or ""):
                    continue
                assert grid_at and grid_at[0] < i, (
                    f"{workflow} job '{job_name}' runs {script} at step {i} "
                    f"with neither '{OSTN15_STEP}' before it nor "
                    f"UKRISK_ALLOW_HELMERT in env")


def test_require_ostn15_refuses_without_the_grid(monkeypatch):
    """The guard itself: a TransformerGroup reporting the OSTN15
    operation as unavailable must stop the build, and the documented
    opt-out must let it through."""
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import build_model as bm
    import pyproj.transformer as pt

    class NoGrid:
        def __init__(self, *a, **k):
            self.unavailable_operations = [
                type("Op", (), {"name": "Inverse of OSGB36 to WGS 84 (9)"})()]
    monkeypatch.setattr(pt, "TransformerGroup", NoGrid)
    monkeypatch.delenv("UKRISK_ALLOW_HELMERT", raising=False)
    with pytest.raises(SystemExit, match="OSTN15"):
        bm.require_ostn15()
    monkeypatch.setenv("UKRISK_ALLOW_HELMERT", "1")
    bm.require_ostn15()
