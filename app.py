# SPDX-FileCopyrightText: 2026 Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GNU GPL v3, section 7): see the file NOTICE.
"""REMEMBER local web interface (Flask). Start it with the run_* launcher."""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import tempfile
import threading
import traceback
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from flask import Flask, abort, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from werkzeug.serving import make_server
from werkzeug.utils import secure_filename

import benchmark_runner as benchmarks
import remember_engine as eng
import trace_io

BASE = Path(__file__).resolve().parent
SAMPLE_DIR = BASE / "data" / "samples"
# Locally REMEMBER listens only on this computer. The hosted image (Dockerfile)
# sets REMEMBER_HOST=0.0.0.0 so that the platform can reach it.
HOST = os.environ.get("REMEMBER_HOST", "127.0.0.1")
DEFAULT_PORT = 7860
MAX_UPLOAD_MB = 500
MAX_KEY_LENGTH = 200
APP_VERSION = "3.7"

# Link of the tool preprint (for example an arXiv page). While it is empty, the
# "Tool preprint" button on the page shows "soon".
PREPRINT_URL = ""

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


@app.after_request
def _no_cache(response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.errorhandler(HTTPException)
def _http_error(exc: HTTPException):
    """Return JSON errors so the page can always show a readable message."""
    if exc.code == 413:
        message = f"The uploaded files are too large (limit: {MAX_UPLOAD_MB} MB in total)."
    else:
        message = exc.description or exc.name
    return jsonify({"error": message}), exc.code


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _allowed(filename: str) -> bool:
    return (filename or "").lower().endswith(trace_io.SUPPORTED_EXTENSIONS)


def _safe_upload_name(filename: str, fallback: str) -> str:
    lower = filename.lower()
    extension = next((ext for ext in trace_io.SUPPORTED_EXTENSIONS if lower.endswith(ext)), "")
    stem = filename[: -len(extension)] if extension else filename
    return (secure_filename(stem) or fallback) + extension


def _log_keys(form: Any) -> trace_io.LogKeys:
    """Case-id, activity and timestamp names typed in the page; empty fields keep the defaults."""
    values: Dict[str, Optional[str]] = {}
    for field, role in (("case", "case id"), ("activity", "activity"), ("timestamp", "timestamp")):
        value = (form.get(f"{field}_key") or "").strip()
        if len(value) > MAX_KEY_LENGTH:
            raise ValueError(f"The {role} name is too long (at most {MAX_KEY_LENGTH} characters).")
        values[field] = value or None
    return trace_io.LogKeys(**values)


def _payload(summary: Dict[str, Any], names: Iterable[str], reference_name: Optional[str]) -> Dict[str, Any]:
    """Result data used by the page and by the CSV export."""
    rows: List[Dict[str, Any]] = []
    count_warnings: List[str] = []
    for name, d in zip(names, summary["details"]):
        rate = d.get("supported_rate")
        rows.append({
            "name": name,
            "reference_name": d.get("reference_name", reference_name),
            "check_name": d.get("check_name", name),
            "uemsc": d.get("uemsc"),
            "entropic_relevance_bits": d.get("entropic_relevance_bits"),
            "predictive_perplexity_supported": d.get("predictive_perplexity_supported"),
            "total": d.get("total"),
            "nonzero": d.get("nonzero"),
            "zero": d.get("zero"),
            "supported_percent": None if rate is None else round(rate * 100.0, 2),
            "scoring_time_s": d.get("scoring_time_s"),
        })
        if d.get("count_warning"):
            count_warnings.append(f"{name}: {d['count_warning']}")

    totals = [r["total"] for r in rows]
    supported = [r["nonzero"] for r in rows]
    aggregate_total = sum(totals) if None not in totals else None
    aggregate_supported = sum(supported) if None not in supported else None
    return {
        "mean": summary.get("mean"),
        "std": summary.get("std"),
        "mean_entropic_relevance_bits": summary.get("mean_entropic_relevance_bits"),
        "mean_predictive_perplexity_supported": summary.get("mean_predictive_perplexity_supported"),
        "n_tests": len(rows),
        "reference_traces": summary.get("reference_traces"),
        "learning_time_s": summary.get("learning_time_s"),
        "total_scoring_time_s": summary.get("total_scoring_time_s"),
        "total_time_s": summary.get("total_time_s"),
        "pipeline": summary.get("pipeline"),
        "aggregate_total": aggregate_total,
        "aggregate_supported": aggregate_supported,
        "aggregate_supported_percent": (
            round(100.0 * aggregate_supported / aggregate_total, 2)
            if aggregate_total and aggregate_supported is not None else None
        ),
        "count_warnings": count_warnings,
        "input_warnings": [str(w) for w in summary.get("input_warnings", []) if w],
        "rows": rows,
    }


def _paper_reference() -> Dict[str, Any]:
    """Published results for the comparison chart; never breaks the page."""
    loader = getattr(benchmarks, "paper_reference", None)
    if loader is None:
        return {}
    try:
        data = loader()
    except Exception:  # noqa: BLE001 - the comparison is optional
        traceback.print_exc()
        return {}
    return data if isinstance(data, dict) else {}


def _error_response(exc: Exception, context: str):
    if isinstance(exc, HTTPException):
        return _http_error(exc)
    if isinstance(exc, eng.EngineNotFound):
        return jsonify({"error": str(exc)}), 503
    if isinstance(exc, (ValueError, FileNotFoundError)):
        return jsonify({"error": str(exc)}), 400
    traceback.print_exc()
    return jsonify({"error": f"{context}: {exc}"}), 500


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template(
        "index.html",
        sample_checks=[p.name for p in sorted(SAMPLE_DIR.glob("check_*.xes"))],
        benchmark_manifest=benchmarks.available_benchmarks(),
        paper_reference=_paper_reference(),
        app_version=APP_VERSION,
        preprint_url=PREPRINT_URL,
    )


def _text_file(*paths: Path):
    """The files as one plain-text page (404 if one is missing)."""
    if not all(p.is_file() for p in paths):
        abort(404)
    text = ("\n\n" + "=" * 78 + "\n\n").join(p.read_text(encoding="utf-8") for p in paths)
    return app.response_class(text, mimetype="text/plain")


@app.route("/license")
def license_text():
    """Copyright notice with the additional terms (NOTICE), then the GNU GPL v3 (LICENSE)."""
    return _text_file(BASE / "NOTICE", BASE / "LICENSE")


@app.route("/third-party-notices")
def third_party_notices():
    """Origin and licences of the Java engine and of the benchmark data."""
    return _text_file(BASE / "THIRD_PARTY_NOTICES.md")


@app.route("/api/ping")
def api_ping():
    return jsonify({"app": "REMEMBER", "version": APP_VERSION})


@app.route("/api/run", methods=["POST"])
def api_run():
    try:
        train = request.files.get("train")
        tests = request.files.getlist("tests")
        if not train or not tests:
            raise ValueError("Please choose one reference log and at least one log to check.")
        if not train.filename or not all(t.filename for t in tests):
            raise ValueError("Each uploaded file must have a file name.")
        if not _allowed(train.filename) or not all(_allowed(t.filename) for t in tests):
            raise ValueError("Unsupported file type. Use .xes, .xes.gz, .csv, .csv.gz, .txt or .txt.gz.")
        keys = _log_keys(request.form)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            train_path = tmp / _safe_upload_name(train.filename, "reference")
            train.save(str(train_path))
            test_paths: List[str] = []
            names: List[str] = []
            for i, uploaded in enumerate(tests):
                path = tmp / f"{i:03d}_{_safe_upload_name(uploaded.filename, f'check_{i}')}"
                uploaded.save(str(path))
                test_paths.append(str(path))
                names.append(Path(uploaded.filename).name)
            summary = eng.run_conformance(
                str(train_path), test_paths,
                reference_label=Path(train.filename).name, check_labels=names, keys=keys,
            )
        payload = _payload(summary, names, Path(train.filename).name)
        payload["input_mode"] = "upload"
        return jsonify(payload)
    except Exception as exc:  # noqa: BLE001 - every error is shown in the page
        return _error_response(exc, "The engine could not process these logs")


@app.route("/api/sample", methods=["POST"])
def api_sample():
    try:
        reference = SAMPLE_DIR / "reference.xes"
        checks = sorted(SAMPLE_DIR.glob("check_*.xes"))
        if not reference.is_file() or not checks:
            raise FileNotFoundError("The example files are missing from data/samples.")
        summary = eng.run_conformance(str(reference), [str(p) for p in checks])
        payload = _payload(summary, [p.name for p in checks], reference.name)
        payload["input_mode"] = "sample"
        return jsonify(payload)
    except Exception as exc:  # noqa: BLE001
        return _error_response(exc, "Could not run the example")


@app.route("/api/benchmark", methods=["POST"])
def api_benchmark():
    try:
        dataset_id = (request.form.get("dataset") or "").strip()
        item = {d["id"]: d for d in benchmarks.available_benchmarks()}.get(dataset_id)
        if item is None:
            raise ValueError("Please choose a benchmark dataset.")
        if not item["installed"]:
            raise FileNotFoundError("The split files of this benchmark are missing from data/benchmarks.")
        summary = benchmarks.run_benchmark(dataset_id)
        payload = _payload(summary, [f"Split {d['benchmark_split'] + 1}" for d in summary["details"]], None)
        payload.update(input_mode="benchmark", benchmark_id=dataset_id, benchmark_name=summary["benchmark_name"])
        return jsonify(payload)
    except Exception as exc:  # noqa: BLE001
        return _error_response(exc, "Could not run the benchmark")


# ---------------------------------------------------------------------------
# Start-up
# ---------------------------------------------------------------------------
def _port_in_use(port: int) -> bool:
    try:
        with socket.create_connection((HOST, port), timeout=0.5):
            return True
    except OSError:
        return False


def _running_remember_version(port: int) -> Optional[str]:
    """Version of a REMEMBER already running on this port ("" if it reports none), else None."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/ping", timeout=2) as response:
            data = json.load(response)
    except (OSError, ValueError):
        return None
    if data.get("app") != "REMEMBER":
        return None
    return str(data.get("version") or "")


def main() -> int:
    try:
        eng.check_setup()
    except eng.EngineNotFound as exc:
        print(f"[REMEMBER] ERROR: {exc}")
        return 1

    try:
        port = int(os.environ.get("REMEMBER_PORT", DEFAULT_PORT))
    except ValueError:
        port = DEFAULT_PORT
    open_browser = os.environ.get("REMEMBER_OPEN_BROWSER") == "1"
    for candidate in range(port, port + 20):
        if not _port_in_use(candidate):
            port = candidate
            break
        running = _running_remember_version(candidate)
        if running == APP_VERSION:
            url = f"http://{HOST}:{candidate}"
            print(f"[REMEMBER] REMEMBER is already running at {url}")
            if open_browser:
                webbrowser.open(url)
            return 0
        if running is not None:
            print(
                f"[REMEMBER] An older REMEMBER window is still running on port {candidate}. "
                "Close it (Ctrl+C in its window) when you can; this version starts on another port."
            )
    else:
        print(f"[REMEMBER] ERROR: no free port found between {port} and {port + 19}.")
        return 1

    # In the Docker image REMEMBER listens on 0.0.0.0, which is not an address
    # for the browser: show localhost instead.
    url = f"http://{'localhost' if HOST == '0.0.0.0' else HOST}:{port}"
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # hide per-request lines
    server = make_server(HOST, port, app, threaded=True)
    print(f"[REMEMBER] Ready: {url}")
    print("[REMEMBER] Keep this window open while you use REMEMBER. Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    print("[REMEMBER] Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
