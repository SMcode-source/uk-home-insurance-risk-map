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
BUILD_WORKFLOWS = ["sector-model.yml", "rebuild.yml", "sw-refetch.yml"]

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


def test_sw_refetch_commits_and_pairs_every_table_it_fetches():
    """The depth bands and the envelope they are conditioned on are two
    rasterisations of the same tile grid. Fetching one without the other
    is what makes the pair unreadable, so every table a job produces must
    be committed by the same run - and the guard must run first."""
    wf = _load("sw-refetch.yml")
    produced = set()
    for job in wf["jobs"].values():
        for step in job.get("steps", []):
            run = step.get("run") or ""
            for f in ("sw_depth.csv", "sw_depth_cc.csv",
                      "sw_fractions_area.csv", "sw_fractions_area_cc.csv"):
                if f"--out data/{f}" in run:
                    produced.add(f)
            if "fetch_sw_depth.py --climate" in run:
                produced.add("sw_depth_cc.csv")
            elif "fetch_sw_depth.py" in run:
                produced.add("sw_depth.csv")
    assert produced == {"sw_depth.csv", "sw_depth_cc.csv",
                        "sw_fractions_area.csv", "sw_fractions_area_cc.csv"}, \
        f"a depth table and its envelope must be refetched together: {produced}"

    steps = wf["jobs"]["collect"]["steps"]
    commit = next(s for s in steps if "git add" in (s.get("run") or ""))
    for f in produced:
        assert f"data/{f}" in commit["run"], f"{f} is fetched but not committed"
    assert "\\n" not in commit["run"]

    guard = next(i for i, s in enumerate(steps)
                 if "pytest" in (s.get("run") or ""))
    assert guard < steps.index(commit), "the guard must run before the commit"
