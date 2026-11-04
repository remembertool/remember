# SPDX-FileCopyrightText: 2026 Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GNU GPL v3, section 7): see the file NOTICE.
"""
benchmark_runner.py - rerun the paper benchmarks (10 paired splits per dataset).

For every split, a new VLMC is learned from the reference part and the matching
check part is scored against it, with the pipeline of the paper (see
remember_engine.py). uEMSC is reported as the mean and the sample standard
deviation (n - 1) over the splits.

The splits are read from data/benchmarks/<dataset>/paper/split_XX_*.txt.gz when
these files are installed. They hold the traces of split_XX_*.xes.gz converted
by the paper's own pipeline, with the same order of events that have equal
timestamps. With them, the results are exactly the published ones on every
computer. Without them, the XES files are converted by this tool; then events
with equal timestamps keep their file order, which can change some values a
little.

Command line (from the package folder, with the .venv Python):

    python benchmark_runner.py                 # list the datasets
    python benchmark_runner.py sepsis          # run one dataset
    python benchmark_runner.py all             # run all datasets
    python benchmark_runner.py all --csv results.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import metrics
import remember_engine as eng

BASE = Path(__file__).resolve().parent
BENCHMARK_ROOT = BASE / "data" / "benchmarks"
MANIFEST_PATH = BENCHMARK_ROOT / "benchmark_manifest.json"
PAPER_REFERENCE_PATH = BENCHMARK_ROOT / "paper_reference_results.json"


def _manifest_datasets() -> List[Dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        return []
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("datasets", [])


def paper_reference() -> Dict[str, Any]:
    """Published uEMSC results (Figs. 4-5 of the paper) used for the comparison chart.

    Returns an empty dict when the file is missing or unreadable, so a run never
    fails because of the comparison data.
    """
    if not PAPER_REFERENCE_PATH.exists():
        return {}
    try:
        return json.loads(PAPER_REFERENCE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _split_files(dataset_id: str, split: Dict[str, Any]) -> Tuple[Optional[Path], Optional[Path], bool]:
    """(reference, check, paper_order) for one split; paths are None when missing."""
    folder = BENCHMARK_ROOT / dataset_id
    index = int(split.get("index", 0))
    paper_ref = folder / "paper" / f"split_{index:02d}_reference.txt.gz"
    paper_chk = folder / "paper" / f"split_{index:02d}_check.txt.gz"
    if paper_ref.is_file() and paper_chk.is_file():
        return paper_ref, paper_chk, True
    xes_ref, xes_chk = folder / split["reference"], folder / split["check"]
    if xes_ref.is_file() and xes_chk.is_file():
        return xes_ref, xes_chk, False
    return None, None, False


def available_benchmarks() -> List[Dict[str, Any]]:
    """Datasets listed in the manifest, and whether all their split files exist."""
    result: List[Dict[str, Any]] = []
    for item in _manifest_datasets():
        splits = item.get("splits", [])
        files = [_split_files(item["id"], s) for s in splits]
        installed = bool(splits) and all(ref is not None for ref, _, _ in files)
        paper_order = installed and all(order for _, _, order in files)
        result.append({
            "id": item["id"], "name": item["name"], "splits": len(splits),
            "installed": installed, "paper_order": paper_order,
            "source_log": item.get("source_log", ""), "description": item.get("description", ""),
            "stats": item.get("stats", {}),
        })
    return result


def run_benchmark(dataset_id: str) -> Dict[str, Any]:
    """Run all splits of one dataset. Times are summed over the splits."""
    dataset = next((d for d in _manifest_datasets() if d.get("id") == dataset_id), None)
    if dataset is None:
        raise ValueError(f"Unknown benchmark dataset: {dataset_id}")
    splits = dataset.get("splits", [])
    if not splits:
        raise ValueError(f"No splits are listed for {dataset['name']}.")

    details: List[Dict[str, Any]] = []
    reference_traces = 0
    learning = scoring = 0.0
    warnings: List[str] = []
    paper_order = True
    started = time.perf_counter()

    for position, split in enumerate(splits):
        reference, check, from_paper = _split_files(dataset_id, split)
        if reference is None or check is None:
            raise FileNotFoundError(
                f"Split files are missing for {dataset['name']}: {split['reference']}, {split['check']}."
            )
        paper_order = paper_order and from_paper
        summary = eng.run_conformance(
            str(reference), [str(check)],
            reference_label=split["reference"], check_labels=[split["check"]],
        )
        detail = dict(summary["details"][0])
        detail.update(
            benchmark_split=int(split.get("index", position)),
            reference_name=split["reference"],
            check_name=split["check"],
        )
        details.append(detail)
        reference_traces += summary["reference_traces"]
        learning += summary["learning_time_s"]
        scoring += summary["total_scoring_time_s"]
        warnings.extend(summary["input_warnings"])

    if not paper_order:
        warnings.append(
            "The paper-order split files (data/benchmarks/<dataset>/paper/) are not installed, so the XES "
            "splits were converted by this tool. Events with equal timestamps keep their file order, so some "
            "values can differ slightly from the paper."
        )

    scores = [d["uemsc"] for d in details]
    return {
        "details": details,
        "mean": statistics.fmean(scores),
        "std": statistics.stdev(scores) if len(scores) > 1 else 0.0,
        "mean_entropic_relevance_bits": metrics.mean(d["entropic_relevance_bits"] for d in details),
        "mean_predictive_perplexity_supported": metrics.mean(
            d["predictive_perplexity_supported"] for d in details
        ),
        "reference_traces": reference_traces,
        "learning_time_s": round(learning, 3),
        "total_scoring_time_s": round(scoring, 3),
        "total_time_s": round(time.perf_counter() - started, 3),
        "pipeline": eng.PIPELINE,
        "paper_order": paper_order,
        "benchmark_id": dataset_id,
        "benchmark_name": dataset["name"],
        "input_warnings": warnings,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Rerun the paper benchmark splits with the paper's pipeline.")
    parser.add_argument("dataset", nargs="?", help="dataset id, or 'all'")
    parser.add_argument("--csv", help="write the per-split results to this CSV file")
    args = parser.parse_args()

    datasets = available_benchmarks()
    if not args.dataset:
        print("Available datasets:")
        for item in datasets:
            print(f"  {item['id']:<24} {item['name']}")
        print("\nExample: python benchmark_runner.py sepsis")
        return 0

    ids = [d["id"] for d in datasets] if args.dataset == "all" else [args.dataset]
    paper = paper_reference().get("datasets", {})
    rows: List[Dict[str, Any]] = []
    print(
        f"{'dataset':<24} {'uEMSC mean':>10} {'SD':>8} {'ER-U':>8} {'time (s)':>9}"
        f" {'paper VLMC':>11} {'best competitor (paper)':>24}"
    )
    for dataset_id in ids:
        result = run_benchmark(dataset_id)
        er = result["mean_entropic_relevance_bits"]
        ref = paper.get(dataset_id) or {}
        best = next((c for c in ref.get("competitors", []) if c.get("id") == ref.get("best_competitor")), None)
        paper_vlmc = f"{ref['vlmc']['mean']:.4f}" if ref.get("vlmc") else "-"
        best_text = f"{best['mean']:.3f} {best['id']}" if best else "-"
        print(
            f"{dataset_id:<24} {result['mean']:>10.4f} {result['std']:>8.4f} "
            f"{'-' if er is None else f'{er:.3f}':>8} {result['total_time_s']:>9.1f}"
            f" {paper_vlmc:>11} {best_text:>24}",
            flush=True,
        )
        for warning in dict.fromkeys(result["input_warnings"]):
            print(f"    note: {warning}")
        for d in result["details"]:
            rows.append({
                "dataset": dataset_id,
                "split": d["benchmark_split"],
                "uEMSC": d["uemsc"],
                "ER_U_bits_per_trace": d["entropic_relevance_bits"],
                "predictive_perplexity": d["predictive_perplexity_supported"],
                "supported_traces": d["nonzero"],
                "total_traces": d["total"],
                "distinct_traces": d.get("distinct_traces"),
            })

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nPer-split results written to {args.csv}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(_main())
    except (ValueError, FileNotFoundError, eng.EngineNotFound) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
