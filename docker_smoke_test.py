# SPDX-FileCopyrightText: 2026 Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GNU GPL v3, section 7): see the file NOTICE.
"""End-to-end check of a running REMEMBER server (used by docker_image.sh test).

It talks to the server only over HTTP, like a browser, and needs only the Python
standard library, so it runs with any Python 3.9+ on the host:
    python3 docker_smoke_test.py --url http://127.0.0.1:17860 [--benchmark bpic13-open-problems]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "samples"
BENCHMARKS = ROOT / "data" / "benchmarks"
TOL = 1e-6

# The same split as verify_sample.py: split 4 of BPIC13 Open Problems (Fig. 4(c)).
PAPER_SPLIT = ("bpic13-open-problems", 3, 0.666917)


def request(url: str, body: bytes = b"", content_type: str = "", timeout: float = 3600) -> Tuple[int, Any]:
    """(HTTP status, decoded JSON or text) of a GET (no body) or POST request."""
    req = urllib.request.Request(url, data=body if content_type else None)
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    text = raw.decode("utf-8")
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


def multipart(fields: Sequence[Tuple[str, Path]], values: Optional[Dict[str, str]] = None) -> Tuple[bytes, str]:
    """Body and Content-Type of a form that uploads these files (and text fields)."""
    boundary = uuid.uuid4().hex
    parts: List[bytes] = []
    for name, value in (values or {}).items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"))
    for name, path in fields:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n".encode("utf-8")
        )
        parts.append(path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def form(fields: Dict[str, str]) -> Tuple[bytes, str]:
    return urllib.parse.urlencode(fields).encode("utf-8"), "application/x-www-form-urlencoded"


def close(actual: Any, target: float, tol: float = TOL) -> bool:
    return actual is not None and math.isfinite(float(actual)) and abs(float(actual) - target) <= tol


def expected_sample() -> List[Dict[str, str]]:
    with (SAMPLE / "expected_results.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def renamed_copies(folder: Path, names: Sequence[str]) -> Tuple[List[Path], List[Path]]:
    """XES and CSV copies of example logs that use other names: 'ticket' for the
    case id, 'step' for the activity and 'when' for the timestamp."""
    rename = {("trace", "concept:name"): "ticket", ("event", "concept:name"): "step", ("event", "time:timestamp"): "when"}
    xes_paths, csv_paths = [], []
    for name in names:
        tree = ET.parse(SAMPLE / name)
        rows = ["ticket,step,when"]
        for trace in tree.getroot():
            if trace.tag.rsplit("}", 1)[-1] != "trace":
                continue
            case = ""
            for child in trace:
                key = child.get("key", "")
                if child.tag.rsplit("}", 1)[-1] != "event":
                    if key == "concept:name":
                        case = child.get("value", "")
                    child.set("key", rename.get(("trace", key), key))
                    continue
                values = {}
                for attribute in child:
                    key = attribute.get("key", "")
                    values[key] = attribute.get("value", "")
                    attribute.set("key", rename.get(("event", key), key))
                rows.append(f"{case},{values.get('concept:name', '')},{values.get('time:timestamp', '')}")
        xes_paths.append(folder / f"renamed_{name}")
        tree.write(xes_paths[-1], encoding="utf-8", xml_declaration=True)
        csv_paths.append(folder / f"renamed_{Path(name).stem}.csv")
        csv_paths[-1].write_text("\n".join(rows) + "\n", encoding="utf-8")
    return xes_paths, csv_paths


def check_custom_names(base: str) -> None:
    """Uploads that use other case-id, activity and timestamp names (XES and CSV)."""
    names = {"case_key": "ticket", "activity_key": "step", "timestamp_key": "when"}
    with tempfile.TemporaryDirectory() as tmp:
        (xes_ref, xes_check), (csv_ref, csv_check) = renamed_copies(Path(tmp), ["reference.xes", "check_1.xes"])
        for kind, ref, check in (("XES", xes_ref, xes_check), ("CSV", csv_ref, csv_check)):
            status, data = request(f"{base}/api/run", *multipart([("train", ref), ("tests", check)], names))
            if status != 200:
                raise AssertionError(f"{kind} upload with chosen names: HTTP {status}, {data}")
            check_sample_rows(f"{kind} upload with chosen names", data, expected_sample()[:1])
        print("PASS  XES and CSV uploads with chosen names (ticket / step / when) give the values of check_1.xes")

        status, data = request(f"{base}/api/run", *multipart([("train", xes_ref), ("tests", xes_check)]))
        if status != 400:
            raise AssertionError(f"renamed XES without chosen names: HTTP {status}, expected 400")
        status, data = request(f"{base}/api/run", *multipart([("train", xes_ref), ("tests", xes_check)],
                                                                dict(names, activity_key="stepp")))
        if status != 400 or "'stepp'" not in str(data.get("error", "")):
            raise AssertionError(f"wrong activity name: HTTP {status}, {data}")
        print(f"PASS  a missing name gives HTTP 400 and says which: {data['error'][:90]}...")


def check_sample_rows(label: str, data: Any, expected: Optional[List[Dict[str, str]]] = None) -> None:
    """The rows of a run must match expected_results.csv (all rows, or the given ones)."""
    rows = data.get("rows", []) if isinstance(data, dict) else []
    expected = expected if expected is not None else expected_sample()
    if len(rows) != len(expected):
        raise AssertionError(f"{label}: {len(rows)} result rows, expected {len(expected)}: {data}")
    for row, want in zip(rows, expected):
        for key, column in (("uemsc", "uEMSC"), ("entropic_relevance_bits", "ER_U_bits_per_trace"),
                            ("predictive_perplexity_supported", "predictive_perplexity_supported")):
            if not close(row.get(key), float(want[column])):
                raise AssertionError(f"{label}: {want['checked_log']} {key} = {row.get(key)!r}, expected {want[column]}")


def run(base: str, benchmark: str) -> None:
    started = time.perf_counter()

    status, data = request(f"{base}/api/ping", timeout=10)
    if status != 200 or data.get("app") != "REMEMBER":
        raise AssertionError(f"ping: HTTP {status}, {data}")
    print(f"PASS  ping: REMEMBER {data.get('version')}")

    status, page = request(f"{base}/", timeout=30)
    if status != 200 or "REMEMBER" not in str(page):
        raise AssertionError(f"page: HTTP {status}")
    print("PASS  page loads (HTTP 200)")

    if "GNU GPL v3 or later" not in str(page) or "Emilio Incerto" not in str(page):
        raise AssertionError("page: the copyright and licence notice is missing")
    status, text = request(f"{base}/license", timeout=10)
    if status != 200 or "Version 3, 29 June 2007" not in str(text) or "Additional terms under section 7" not in str(text):
        raise AssertionError(f"/license: HTTP {status}, not the NOTICE and the GNU GPL v3 text")
    status, text = request(f"{base}/third-party-notices", timeout=10)
    if status != 200 or "# Third-party notices" not in str(text):
        raise AssertionError(f"/third-party-notices: HTTP {status}")
    print("PASS  licence notice on the page; /license (GNU GPL v3) and /third-party-notices are served")

    status, data = request(f"{base}/api/sample", *form({}))
    if status != 200:
        raise AssertionError(f"bundled example: HTTP {status}, {data}")
    check_sample_rows("bundled example", data)
    print(f"PASS  bundled example gives expected_results.csv: uEMSC {[r['uemsc'] for r in data['rows']]}")

    checks = sorted(SAMPLE.glob("check_*.xes"))
    status, data = request(f"{base}/api/run", *multipart([("train", SAMPLE / "reference.xes")] + [("tests", p) for p in checks]))
    if status != 200:
        raise AssertionError(f"upload of the example XES files: HTTP {status}, {data}")
    check_sample_rows("upload of the example XES files", data)
    print("PASS  upload of the example XES files gives the same values")

    dataset, index, target = PAPER_SPLIT
    folder = BENCHMARKS / dataset / "paper"
    files = [("train", folder / f"split_{index:02d}_reference.txt.gz"), ("tests", folder / f"split_{index:02d}_check.txt.gz")]
    status, data = request(f"{base}/api/run", *multipart(files))
    actual = data["rows"][0]["uemsc"] if status == 200 else None
    if not close(actual, target):
        raise AssertionError(f"upload of {dataset} split {index + 1}: HTTP {status}, uEMSC {actual!r}, expected {target}")
    print(f"PASS  upload of {dataset} split {index + 1} (txt.gz) gives the paper's value {target}")

    check_custom_names(base)

    if benchmark:
        reference = json.loads((BENCHMARKS / "paper_reference_results.json").read_text(encoding="utf-8"))
        paper_mean = reference["datasets"][benchmark]["vlmc"]["mean"]
        t0 = time.perf_counter()
        status, data = request(f"{base}/api/benchmark", *form({"dataset": benchmark}))
        if status != 200 or not close(data.get("mean"), paper_mean, tol=5e-4):
            raise AssertionError(f"benchmark {benchmark}: HTTP {status}, mean {data.get('mean') if isinstance(data, dict) else data!r}, paper {paper_mean}")
        print(f"PASS  benchmark {benchmark}: uEMSC {data['mean']:.4f} ± {data['std']:.4f} "
              f"(paper {paper_mean}) in {time.perf_counter() - t0:.0f} s")

    print(f"All HTTP checks passed in {time.perf_counter() - started:.0f} s.")


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end HTTP check of a running REMEMBER server.")
    parser.add_argument("--url", default="http://127.0.0.1:7860", help="server address (default: %(default)s)")
    parser.add_argument("--benchmark", default="", help="also run this paper benchmark, e.g. bpic13-open-problems")
    args = parser.parse_args()
    try:
        run(args.url.rstrip("/"), args.benchmark)
    except (AssertionError, OSError, KeyError, ValueError) as exc:
        print(f"FAIL  {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
