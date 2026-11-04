# SPDX-FileCopyrightText: 2026 Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GNU GPL v3, section 7): see the file NOTICE.
"""
remember_engine.py - run the VLMC pipeline of the paper with the bundled Java engine.

The pipeline is the one of the paper's replication code (Incerto, Vandin, Sarv Ahrabi,
Information Systems 133, 2025; github.com/bistrulli/remember, vlmcProcessMining.py):

1. convert the reference log and the check logs to the trace format of the paper
   (trace_io.py: "!$ activity$ ... end$");
2. build the flow graph (ECF) of the reference log with engine/trace2ecf-paper.jar
   and learn one VLMC from the reference log with engine/jfitVlmc-paper.jar.
   The engine runs with the setting of the paper: no pruning. (In this engine
   version this is the command-line value "--alfa 1"; it is fixed, not a choice.)
3. for every check log, compute the likelihood M(t) of each distinct trace t
   with the learned VLMC, and uEMSC exactly as the paper's code does:
       uEMSC = 1 - sum over distinct traces t of max(round(L(t), 6) - round(M(t), 6), 0)
   where L(t) is the frequency of t in the check log. The engine prints M(t)
   with 6 decimals, as in the paper;
4. compute trace support, ER-U and predictive perplexity from the
   full-precision likelihoods (metrics.py). These do not change uEMSC.
"""

from __future__ import annotations

import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

import java_runtime
import metrics
import trace_io

BASE = Path(__file__).resolve().parent
JAR = BASE / "engine" / "jfitVlmc-paper.jar"
ECF_JAR = BASE / "engine" / "trace2ecf-paper.jar"
ENGINE_TIMEOUT_S = 3600
# Fixed setting of the paper's experiments (no pruning; one simulated trace).
PAPER_SETTING = ["--nsim", "1", "--ntime", "1", "--alfa", "1"]
# Let large logs use more memory than the Java default (a quarter of the RAM).
JAVA_OPTIONS = ["-XX:MaxRAMPercentage=60"]
PIPELINE = "paper pipeline (no pruning)"
_RUN_LOCK = threading.Lock()


class EngineNotFound(RuntimeError):
    """Raised when Java 17+ or an engine JAR is missing."""


def check_setup() -> Tuple[str, int]:
    """Return (java path, java version); raise EngineNotFound if something is missing."""
    for jar in (JAR, ECF_JAR):
        if not jar.is_file():
            raise EngineNotFound(
                f"The engine file engine/{jar.name} is missing. Please use a complete copy of the package."
            )
    try:
        return java_runtime.find_java()
    except java_runtime.JavaNotFound as exc:
        raise EngineNotFound(str(exc)) from exc


def _run_java(java: str, jar: Path, args: List[str], cwd: Path) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            [java, *JAVA_OPTIONS, "-jar", str(jar), *args],
            capture_output=True, text=True, cwd=str(cwd), timeout=ENGINE_TIMEOUT_S, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"The engine did not finish within {ENGINE_TIMEOUT_S // 60} minutes.") from exc
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    return proc.returncode, output


def _tail(text: str, limit: int = 1500) -> str:
    lines = [line for line in (text or "").splitlines() if not line.startswith("Picked up JAVA_TOOL_OPTIONS")]
    return "\n".join(lines)[-limit:]


def stochastic_language(traces: Sequence[str]) -> Tuple[List[str], List[int]]:
    """Distinct traces in order of first appearance, with their counts."""
    counts: Dict[str, int] = {}
    for trace in traces:
        counts[trace] = counts.get(trace, 0) + 1
    distinct = list(counts)
    return distinct, [counts[t] for t in distinct]


def paper_uemsc(frequencies: Sequence[float], model_likelihoods_6dp: Sequence[float]) -> float:
    """uEMSC as computed by computeMuEMSC() in the paper's code."""
    tl = np.round(np.asarray(frequencies, dtype=float), 6)
    ml = np.round(np.asarray(model_likelihoods_6dp, dtype=float), 6)
    value = float(1 - np.sum(np.maximum(tl - ml, 0)))
    return 0.0 if abs(value) < 1e-12 else value  # e.g. -2e-16 from float rounding


def _read_likelihoods(path: Path, expected: int) -> Tuple[List[float], List[Optional[float]]]:
    """Read the engine's likelihood file: 6-decimal value, length, full-precision value."""
    short: List[float] = []
    full: List[Optional[float]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.strip().split(",")
        if len(parts) < 2 or not parts[0]:
            continue
        short.append(float(parts[0]))
        try:
            full.append(float(parts[2]) if len(parts) > 2 else float(parts[0]))
        except ValueError:
            full.append(None)
    if len(short) != expected:
        raise RuntimeError(
            f"The engine returned {len(short)} likelihood values for {expected} distinct traces."
        )
    return short, full


def run_conformance(
    reference_path: str,
    check_paths: List[str],
    reference_label: Optional[str] = None,
    check_labels: Optional[List[str]] = None,
    keys: Optional[trace_io.LogKeys] = None,
) -> Dict[str, Any]:
    """Learn a VLMC from the reference log and score every check log against it.

    `keys` names the case-id, activity and timestamp attributes or columns of
    all the logs (None: the defaults of trace_io). Times are wall-clock seconds
    on this computer (including Java start-up).
    """
    java, _ = check_setup()
    if not check_paths:
        raise ValueError("At least one log to check is required.")
    labels = list(check_labels or [Path(p).name for p in check_paths])

    with _RUN_LOCK, tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        started = time.perf_counter()
        input_warnings: List[str] = []

        # 1. Convert the logs.
        reference = trace_io.load_traces(
            reference_path, warnings=input_warnings, source_label=reference_label or Path(reference_path).name,
            keys=keys,
        )
        trace_io.write_traces(reference, tmp / "train.txt")
        checks = [
            trace_io.load_traces(path, warnings=input_warnings, source_label=label, keys=keys)
            for path, label in zip(check_paths, labels)
        ]
        preparation_time = time.perf_counter() - started

        # 2. Flow graph + VLMC from the reference log only.
        learning_started = time.perf_counter()
        code, output = _run_java(java, ECF_JAR, ["--ecfInDir", "train.txt", "--ecfOutDir", "train.ecf"], tmp)
        if code != 0 or not (tmp / "train.ecf").is_file():
            raise RuntimeError("The engine could not build the flow graph of the reference log.\n" + _tail(output))
        learn_args = ["--ecf", "train.ecf", "--outfile", "out.mat", "--infile", "train.txt", "--vlmcfile", "model.vlmc"]
        code, output = _run_java(java, JAR, [*learn_args, *PAPER_SETTING], tmp)
        if code != 0 or not (tmp / "model.vlmc").is_file():
            raise RuntimeError("The engine could not learn a VLMC from the reference log.\n" + _tail(output))
        learning_time = time.perf_counter() - learning_started

        # 3. Score every check log.
        score_args = ["--ecf", "train.ecf", "--outfile", "out.mat", "--infile", "train.txt",
                      "--vlmcfile", "model_unused.vlmc", *PAPER_SETTING, "--vlmc", "model.vlmc"]
        lik_file = tmp / "model.vlmc.lik"
        details: List[Dict[str, Any]] = []
        for i, (traces, label) in enumerate(zip(checks, labels)):
            scoring_started = time.perf_counter()
            distinct, counts = stochastic_language(traces)
            total = len(traces)
            lan = tmp / f"check_{i}.lan"
            lan.write_text(" ".join(distinct) + "\n", encoding="ascii")
            lik_file.unlink(missing_ok=True)
            code, output = _run_java(java, JAR, [*score_args, "--lik", lan.name], tmp)
            if code != 0 or not lik_file.is_file():
                raise RuntimeError(f"The engine could not score {label}.\n" + _tail(output))
            short, full = _read_likelihoods(lik_file, len(distinct))

            detail: Dict[str, Any] = {
                "uemsc": paper_uemsc([c / total for c in counts], short),
                "distinct_traces": len(distinct),
            }
            detail.update(metrics.likelihood_metrics(distinct, counts, full))
            detail["scoring_time_s"] = round(time.perf_counter() - scoring_started, 3)
            details.append(detail)

        scoring_time = sum(d["scoring_time_s"] for d in details)
        return {
            "details": details,
            "mean": metrics.mean(d["uemsc"] for d in details),
            "mean_entropic_relevance_bits": metrics.mean(d["entropic_relevance_bits"] for d in details),
            "mean_predictive_perplexity_supported": metrics.mean(
                d["predictive_perplexity_supported"] for d in details
            ),
            "reference_traces": len(reference),
            "preparation_time_s": round(preparation_time, 3),
            "learning_time_s": round(learning_time, 3),
            "total_scoring_time_s": round(scoring_time, 3),
            "total_time_s": round(time.perf_counter() - started, 3),
            "pipeline": PIPELINE,
            "input_warnings": input_warnings,
        }
