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
import os

import pytest
import yaml

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")

# Scripts that transform WGS84 to British National Grid and must see the
# same OSTN15 grid the model build uses (HANDOFF 2026-09-05: the grid was
# the whole of the local-vs-CI gap).
NEEDS_OSTN15 = ("fetch_onspd.py", "score_subsidence_postcodes.py",
                "build_model.py")
OSTN15_STEP = "Install the OSTN15 datum grid"


def _load(name):
    with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _steps_running(job, script):
    for i, step in enumerate(job.get("steps", [])):
        run = step.get("run") or ""
        if script in run:
            yield i, step


@pytest.mark.parametrize("workflow", ["sector-model.yml", "rebuild.yml"])
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
