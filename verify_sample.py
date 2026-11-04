# SPDX-FileCopyrightText: 2026 Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GNU GPL v3, section 7): see the file NOTICE.
"""Check that this installation reproduces the reference results of the package.

Run with the Python of the .venv folder:
    macOS / Linux:  .venv/bin/python verify_sample.py
    Windows:        .venv\\Scripts\\python.exe verify_sample.py
"""

from __future__ import annotations

import csv
import math
import platform
import sys
import tempfile
from pathlib import Path

import benchmark_runner
import remember_engine as eng
import trace_io

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "samples"
TOL = 1e-6

# One benchmark split with a value that is visible in the paper: split 4 of
# BPIC13 Open Problems is the outlier (0.6669) of the VLMC box in Fig. 4(c).
PAPER_SPLIT = ("bpic13-open-problems", 3, 0.666917)


def close(actual, target, tol=TOL) -> bool:
    return actual is not None and math.isfinite(float(actual)) and abs(float(actual) - float(target)) <= tol


def verify_bundled_sample() -> None:
    """The example logs must give the values stored in expected_results.csv."""
    with (SAMPLE / "expected_results.csv").open(newline="", encoding="utf-8") as handle:
        expected = list(csv.DictReader(handle))

    checks = [SAMPLE / row["checked_log"] for row in expected]
    result = eng.run_conformance(str(SAMPLE / "reference.xes"), [str(p) for p in checks])

    failures = []
    for row, detail in zip(expected, result["details"]):
        name = row["checked_log"]
        comparisons = {
            "uEMSC": (detail["uemsc"], row["uEMSC"]),
            "ER-U": (detail["entropic_relevance_bits"], row["ER_U_bits_per_trace"]),
            "predictive perplexity": (detail["predictive_perplexity_supported"], row["predictive_perplexity_supported"]),
        }
        for label, (actual, target) in comparisons.items():
            if not close(actual, target):
                failures.append(f"{name}: {label} = {actual!r}, expected {target}")
        if detail["nonzero"] != int(row["supported_traces"]):
            failures.append(f"{name}: supported traces = {detail['nonzero']!r}, expected {row['supported_traces']}")

    if failures:
        raise AssertionError("Example results differ:\n" + "\n".join(failures))
    print("PASS  example logs give the expected results (expected_results.csv)")


def verify_paper_split() -> None:
    """One benchmark split must give exactly the value of the paper's pipeline."""
    dataset_id, index, target = PAPER_SPLIT
    folder = benchmark_runner.BENCHMARK_ROOT / dataset_id / "paper"
    reference = folder / f"split_{index:02d}_reference.txt.gz"
    check = folder / f"split_{index:02d}_check.txt.gz"
    if not (reference.is_file() and check.is_file()):
        print("SKIP  paper-order benchmark files are not installed (data/benchmarks/<dataset>/paper/)")
        return
    actual = eng.run_conformance(str(reference), [str(check)])["details"][0]["uemsc"]
    if not close(actual, target):
        raise AssertionError(f"Benchmark split check failed: uEMSC = {actual!r}, expected {target}.")
    print(f"PASS  {dataset_id} split {index + 1} gives the paper's value ({target:.4f}, Fig. 4(c))")


def verify_first_activity() -> None:
    """Different first-activity frequencies must lower uEMSC (expected value 0.6)."""
    with tempfile.TemporaryDirectory() as td:
        ref, chk = Path(td) / "reference.txt", Path(td) / "check.txt"
        ref.write_text("A X end$ " * 50 + "B X end$ " * 50, encoding="utf-8")
        chk.write_text("A X end$ " * 90 + "B X end$ " * 10, encoding="utf-8")
        actual = eng.run_conformance(str(ref), [str(chk)])["details"][0]["uemsc"]
    if not close(actual, 0.6):
        raise AssertionError(f"First-activity check failed: uEMSC = {actual!r}, expected 0.6.")
    print("PASS  the first activity of each trace is part of the likelihood")


def verify_labels() -> None:
    """Labels are cleaned like in the paper; 'nan', 'none' and 'null' stay ordinary labels."""
    cases = {
        "ER Registration": "ERRegistration$",
        "O_Create Offer": "OCreateOffer$",
        "A-B+C.D;E(F)": "ABCDEF$",
        "nan": "nan$",
        "null": "null$",
    }
    for label, token in cases.items():
        if trace_io.engine_label(label) != token:
            raise AssertionError(f"Label {label!r} became {trace_io.engine_label(label)!r}, expected {token!r}.")
    if trace_io.engine_label("Accepted/In Progress") == trace_io.engine_label("Accepted/In-Progress!"):
        raise AssertionError("Different labels with special characters must stay different.")

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "labels.csv"
        csv_path.write_text("case_id,activity\n1,nan\n1,none\n1,null\n", encoding="utf-8")
        traces = trace_io.load_traces(csv_path)
    if traces != ["!$ nan$ none$ null$ end$"]:
        raise AssertionError(f"CSV labels were not kept: {traces!r}")
    print("PASS  activity labels are cleaned like in the paper (nan / none / null are kept)")


_CUSTOM_XES = """<?xml version="1.0" encoding="utf-8" ?>
<log xmlns="http://www.xes-standard.org/">
  <trace><string key="ticket" value="T2" />
    <event><string key="step" value="Close" /><string key="concept:name" value="other" /><date key="when" value="2024-01-01T11:00:00+00:00" /></event>
    <event><string key="step" value="Open" /><string key="concept:name" value="other" /><date key="when" value="2024-01-01T10:00:00+00:00" /></event>
  </trace>
  <trace><string key="ticket" value="T1" />
    <event><string key="step" value="Open" /><date key="when" value="2024-01-01T08:00:00+00:00" /></event>
  </trace>
</log>
"""

_EVENT_CASE_XES = """<?xml version="1.0" encoding="utf-8" ?>
<log xmlns="http://www.xes-standard.org/">
  <trace><string key="concept:name" value="all" />
    <event><string key="ticket" value="B" /><string key="concept:name" value="Y" /></event>
    <event><string key="ticket" value="A" /><string key="concept:name" value="X" /></event>
    <event><string key="ticket" value="B" /><string key="concept:name" value="Z" /></event>
  </trace>
</log>
"""

_CUSTOM_CSV = "ticket;step;when\nT2;Close;2024-01-01T11:00:00Z\nT2;Open;2024-01-01T10:00:00Z\nT1;Open;2024-01-01T08:00:00Z\n"


def verify_custom_names() -> None:
    """Case-id, activity and timestamp names chosen by the user (XES attributes, CSV columns)."""
    keys = trace_io.LogKeys(case="ticket", activity="step", timestamp="when")
    expected = ["!$ Open$ end$", "!$ Open$ Close$ end$"]
    with tempfile.TemporaryDirectory() as td:
        xes, by_event, table = Path(td) / "custom.xes", Path(td) / "by_event.xes", Path(td) / "custom.csv"
        xes.write_text(_CUSTOM_XES, encoding="utf-8")
        by_event.write_text(_EVENT_CASE_XES, encoding="utf-8")
        table.write_text(_CUSTOM_CSV, encoding="utf-8")

        for path in (xes, table):
            traces = trace_io.load_traces(path, keys=keys)
            if traces != expected:
                raise AssertionError(f"{path.name} with chosen names gave {traces!r}, expected {expected!r}.")
        traces = trace_io.load_traces(by_event, keys=trace_io.LogKeys(case="ticket"))
        if traces != ["!$ X$ end$", "!$ Y$ Z$ end$"]:
            raise AssertionError(f"Grouping by an event attribute gave {traces!r}.")

        for path, wrong in ((xes, trace_io.LogKeys(activity="stepp")), (table, trace_io.LogKeys(activity="stepp")),
                            (table, trace_io.LogKeys())):
            try:
                trace_io.load_traces(path, keys=wrong)
            except ValueError as exc:
                if wrong.activity and wrong.activity not in str(exc):
                    raise AssertionError(f"The error for a missing name does not show it: {exc}") from exc
            else:
                raise AssertionError(f"{path.name} with names {wrong} should give an error.")
    print("PASS  chosen case-id, activity and timestamp names are used (XES and CSV)")


if __name__ == "__main__":
    java, version = eng.check_setup()
    print(f"Python {platform.python_version()} on {platform.system()} {platform.machine()}; Java {version} ({java})")
    try:
        verify_bundled_sample()
        verify_paper_split()
        verify_first_activity()
        verify_labels()
        verify_custom_names()
    except AssertionError as exc:
        print(f"FAIL  {exc}")
        sys.exit(1)
    print("All checks passed.")
