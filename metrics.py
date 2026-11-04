# SPDX-FileCopyrightText: 2026 Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GNU GPL v3, section 7): see the file NOTICE.
"""
metrics.py - diagnostics computed from the trace likelihoods of the engine.

uEMSC itself is computed in remember_engine.py exactly as in the paper. This
module adds three diagnostics; they never change uEMSC. They use the
full-precision likelihood M(t) of each distinct trace t of the checked log,
weighted by how often t occurs.

trace support
    Share of checked trace instances with non-zero VLMC likelihood.

ER-U (Entropic Relevance, uniform background), in bits per trace
    Alkhammash et al., Information Systems 107 (2022) 101922.
        ER-U = H0(rho) + (1/|E|) * sum over traces t of cost(t)
    cost(t) = -log2 M(t)                          if M(t) > 0
    cost(t) = (|t| + 1) * log2(|alphabet| + 1)    otherwise (uniform background)
    rho is the trace support, H0 the binary entropy, and the alphabet is the
    set of activities of the checked log (+1 for the end-of-trace symbol).

Predictive perplexity (diagnostic only)
    exp(-sum log M(t) / number of predicted symbols), over supported traces.
    Every activity and the end symbol are predicted (|t| + 1 symbols per
    trace), because the "!$" start token is the first context.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence

import trace_io


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    """Mean of the finite values, or None when there are none."""
    clean = [v for v in (_finite(x) for x in values) if v is not None]
    return sum(clean) / len(clean) if clean else None


def binary_entropy_bits(p: float) -> float:
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p)


def likelihood_metrics(
    distinct_traces: Sequence[str],
    counts: Sequence[int],
    likelihoods: Sequence[Optional[float]],
) -> Dict[str, Any]:
    """Trace support, ER-U and predictive perplexity for one checked log."""
    total = int(sum(counts))
    result: Dict[str, Any] = {
        "total": total,
        "nonzero": None,
        "zero": None,
        "supported_rate": None,
        "entropic_relevance_bits": None,
        "predictive_perplexity_supported": None,
        "count_warning": None,
    }
    if total <= 0:
        return result

    activities: List[List[str]] = [trace_io.activities_of(t) for t in distinct_traces]
    alphabet = {a for acts in activities for a in acts}
    background_symbol_bits = math.log2(max(len(alphabet) + 1, 2))

    supported = 0
    cost_bits = 0.0
    supported_loglik = 0.0
    predictions = 0
    for acts, count, likelihood in zip(activities, counts, likelihoods):
        symbols = len(acts) + 1
        if likelihood is not None and likelihood > 0.0:
            loglik = math.log(likelihood)
            supported += count
            cost_bits += count * (-loglik / math.log(2))
            supported_loglik += count * loglik
            predictions += count * symbols
        else:
            cost_bits += count * symbols * background_symbol_bits

    rho = supported / total
    result.update(
        nonzero=supported,
        zero=total - supported,
        supported_rate=rho,
        entropic_relevance_bits=binary_entropy_bits(rho) + cost_bits / total,
    )
    if predictions > 0:
        exponent = -supported_loglik / predictions
        result["predictive_perplexity_supported"] = math.exp(exponent) if exponent < 700 else math.inf
    return result
