# SPDX-FileCopyrightText: 2026 Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GNU GPL v3, section 7): see the file NOTICE.
"""
trace_io.py - convert event logs into the trace format of the paper's VLMC pipeline.

Every trace is written as

    !$ activity_1$ activity_2$ ... end$

exactly as in the replication code of the paper (Incerto, Vandin, Sarv Ahrabi,
Information Systems 133, 2025; github.com/bistrulli/remember, vlmcProcessMining.py):

- "!$" starts every trace. The engine uses it as context, so the probability of
  the first activity is part of the trace likelihood;
- events are ordered by timestamp. Events with the same timestamp keep their
  order in the file (stable sort);
- cases are written in sorted order of their case id;
- activity labels lose the characters  whitespace _ & $ ( ) { } [ ] - + . ; '
  and get a "$" at the end.

After this cleaning, a label that still contains a character other than a
letter or a digit (for example "/" or "é") is made safe for the engine: these
characters are removed and a short hash of the original label is added, so
different labels stay different. The benchmark datasets never need this step.

Supported inputs (control-flow perspective only):

- XES / XES.GZ  - read with the Python standard library
- CSV / CSV.GZ  - case-id, activity and optional timestamp columns are detected
- TXT / TXT.GZ  - traces separated by "end$". A file that is already in the
                  format above (it starts with "!$") is used unchanged; this is
                  how the benchmark splits keep the exact event order of the paper.

For XES and CSV the user can name other attributes (XES) or columns (CSV) for
the case id, the activity and the timestamp (LogKeys).
"""

from __future__ import annotations

import gzip
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd

START = "!$"
END = "end$"

# Characters removed by the paper's pipeline (vlmcProcessMining.processXesFile).
_PAPER_CLEAN_RE = re.compile(r"[\s_&$(){}\[\]\-\+\.;']+")
# After that cleaning, only letters and digits are passed to the engine unchanged.
_UNSAFE_RE = re.compile(r"[^A-Za-z0-9]")
_MAX_LABEL_LENGTH = 80
_PAPER_TOKEN_RE = re.compile(r"^[A-Za-z0-9!#]*\$$")

_CASE_CANDIDATES = [
    "case_id", "caseid", "case", "case:concept:name", "trace_id", "traceid",
]
_ACTIVITY_CANDIDATES = [
    "activity", "concept:name", "event", "event_name", "task", "name",
]
_TIMESTAMP_CANDIDATES = [
    "timestamp", "time:timestamp", "time", "datetime", "date", "complete_timestamp",
]

SUPPORTED_EXTENSIONS = (".xes", ".xes.gz", ".csv", ".csv.gz", ".txt", ".txt.gz")

# Standard XES keys: concept:name of the <trace> (case id), concept:name and
# time:timestamp of each <event>.
_XES_CASE_KEY = "concept:name"
_XES_ACTIVITY_KEY = "concept:name"
_XES_TIMESTAMP_KEY = "time:timestamp"


@dataclass(frozen=True)
class LogKeys:
    """Names chosen by the user for the case id, the activity and the timestamp.

    They are attribute keys for XES and column names for CSV; TXT logs ignore
    them. None keeps the default: the standard XES keys, or automatic detection
    of the CSV columns.
    """

    case: Optional[str] = None
    activity: Optional[str] = None
    timestamp: Optional[str] = None


DEFAULT_KEYS = LogKeys()


# ---------------------------------------------------------------------------
# Activity labels
# ---------------------------------------------------------------------------
def _hash(text: str) -> str:
    return "H" + hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:8]


def engine_label(label: object) -> str:
    """Map an activity label to an engine token (deterministic, ends with "$")."""
    original = str(label).strip()
    cleaned = _PAPER_CLEAN_RE.sub("", original)
    if not cleaned or _UNSAFE_RE.search(cleaned) or len(cleaned) > _MAX_LABEL_LENGTH or cleaned == "end":
        cleaned = _UNSAFE_RE.sub("", cleaned)[: _MAX_LABEL_LENGTH - 9] + _hash(original)
    return cleaned + "$"


def _trace_text(activities: Sequence[object]) -> str:
    return " ".join([START, *(engine_label(a) for a in activities), END])


# ---------------------------------------------------------------------------
# Table -> traces (XES and CSV)
# ---------------------------------------------------------------------------
def _parse_timestamps(raw: pd.Series) -> pd.Series:
    """Parse timestamps to UTC. ISO 8601 first, then a per-value fallback."""
    parsed = pd.to_datetime(raw, errors="coerce", utc=True, format="ISO8601")
    failed = parsed.isna() & raw.notna() & raw.astype(str).str.strip().ne("")
    if failed.any():
        retry = pd.to_datetime(raw[failed], errors="coerce", utc=True, format="mixed")
        parsed.loc[failed] = retry
    return parsed


def _table_to_traces(
    df: pd.DataFrame,
    case_col: str,
    act_col: str,
    ts_col: Optional[str],
    *,
    warnings: Optional[List[str]],
    source_label: str,
) -> List[str]:
    """Group events into traces in the order of the paper's pipeline.

    Events are sorted by timestamp (stable: ties keep the file order; events
    without a usable timestamp go to the end of their case). Cases follow the
    sorted order of their case id, as pandas groupby does in the paper's code.
    """
    columns = [c for c in (case_col, act_col, ts_col) if c]
    work = df[columns].copy()
    rows = len(work)
    work = work.dropna(subset=[case_col, act_col])
    work = work[
        work[case_col].astype(str).str.strip().ne("")
        & work[act_col].astype(str).str.strip().ne("")
    ]
    dropped = rows - len(work)
    if dropped and warnings is not None:
        warnings.append(f"{source_label}: {dropped} event(s) without a case id or an activity name were skipped.")

    work[case_col] = work[case_col].astype(str)
    if ts_col:
        raw = work[ts_col]
        parsed = _parse_timestamps(raw)
        nonempty = raw.notna() & raw.astype(str).str.strip().ne("")
        invalid = int((nonempty & parsed.isna()).sum())
        work = work.assign(**{ts_col: parsed})
        work = work.sort_values(ts_col, kind="stable", na_position="last")
        if warnings is not None and invalid:
            warnings.append(
                f"{source_label}: {invalid} of {int(nonempty.sum())} timestamp value(s) could "
                "not be read. These events were placed at the end of their case, in file order."
            )

    traces: Dict[str, List[object]] = {}
    for case, activity in zip(work[case_col].tolist(), work[act_col].tolist()):
        traces.setdefault(case, []).append(activity)
    return [_trace_text(traces[case]) for case in sorted(traces)]


# ---------------------------------------------------------------------------
# XES
# ---------------------------------------------------------------------------
def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _key_list(keys: Iterable[Optional[str]]) -> str:
    names = sorted(k for k in set(keys) if k)
    return ", ".join(names[:30]) + (", ..." if len(names) > 30 else "") if names else "none"


def _read_xes_table(path: str, keys: LogKeys = DEFAULT_KEYS) -> pd.DataFrame:
    """Read the events of an XES file into a table (case id, activity, time).

    By default the case id is the concept:name of the <trace>; the activity and
    the time are the concept:name and time:timestamp attributes of each <event>.
    `keys` can name other attributes. A chosen case-id key is read from the
    <trace> and, for traces without it, from each event, so events can also be
    grouped by an event attribute; events without it are then skipped.
    Nested attributes and log-level <global> defaults are ignored.
    """
    case_key = keys.case or _XES_CASE_KEY
    activity_key = keys.activity or _XES_ACTIVITY_KEY
    time_key = keys.timestamp or _XES_TIMESTAMP_KEY
    # On events, concept:name is the activity, never a case id.
    event_case_key = keys.case if keys.case != _XES_CASE_KEY else None
    opener = gzip.open if path.lower().endswith(".gz") else open
    cases: List[Optional[str]] = []
    event_cases: List[Optional[str]] = []
    activities: List[Optional[str]] = []
    timestamps: List[Optional[str]] = []
    trace_keys: set = set()
    event_keys: set = set()

    stack: List[str] = []
    trace_number = -1
    trace_start = 0
    case_id: Optional[str] = None
    event_case: Optional[str] = None
    activity: Optional[str] = None
    timestamp: Optional[str] = None
    root = None

    with opener(path, "rb") as handle:
        for event, elem in ET.iterparse(handle, events=("start", "end")):
            tag = _local_name(elem.tag)
            if event == "start":
                if root is None:
                    root = elem
                if tag == "trace" and stack and stack[-1] == "log":
                    trace_number += 1
                    trace_start = len(cases)
                    case_id = None
                elif tag == "event" and stack and stack[-1] == "trace":
                    event_case, activity, timestamp = None, None, None
                stack.append(tag)
                continue

            stack.pop()
            parent = stack[-1] if stack else None
            if parent == "trace" and tag != "event":
                key = elem.get("key")
                trace_keys.add(key)
                if key == case_key:
                    case_id = elem.get("value")
            elif parent == "event" and len(stack) >= 2 and stack[-2] == "trace":
                key = elem.get("key")
                event_keys.add(key)
                if key == activity_key:
                    activity = elem.get("value")
                if key == time_key:
                    timestamp = elem.get("value")
                if event_case_key and key == event_case_key:
                    event_case = elem.get("value")
            elif tag == "event" and parent == "trace":
                cases.append(None)
                event_cases.append(event_case)
                activities.append(activity)
                timestamps.append(timestamp)
            elif tag == "trace" and parent == "log":
                # The trace name can appear before or after the events.
                for i in range(trace_start, len(cases)):
                    if case_id is not None:
                        cases[i] = case_id
                    elif event_case_key:
                        cases[i] = event_cases[i]
                    else:
                        cases[i] = f"__trace_{trace_number}"
                elem.clear()
                if root is not None:
                    root.clear()

    if root is None or _local_name(root.tag) != "log":
        raise ValueError("not a valid XES log (the root element must be <log>).")

    found = (f"Trace attributes in this file: {_key_list(trace_keys)}. "
             f"Event attributes: {_key_list(event_keys)}.")
    if keys.case and keys.case not in trace_keys | event_keys:
        raise ValueError(f"no trace or event has the case-id attribute '{keys.case}'. {found}")
    if activity_key not in event_keys:
        hint = "" if keys.activity else " Other names can be entered under 'Column and attribute names'."
        raise ValueError(f"no event has the activity attribute '{activity_key}'. {found}{hint}")
    if keys.timestamp and keys.timestamp not in event_keys:
        raise ValueError(f"no event has the timestamp attribute '{keys.timestamp}'. {found}")

    return pd.DataFrame({"case": cases, "activity": activities, "timestamp": timestamps})


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
def _normalise_column(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())


def _find_column(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    """Find a column by common names, ignoring case, spaces and punctuation."""
    normalised = {_normalise_column(col): col for col in columns}
    for candidate in candidates:
        hit = normalised.get(_normalise_column(candidate))
        if hit is not None:
            return hit
    return None


def _csv_column(columns: Sequence[str], chosen: Optional[str], candidates: Sequence[str], role: str) -> Optional[str]:
    """The column named by the user (exact name first, then ignoring case and
    punctuation), or the column found among the common names."""
    if not chosen:
        return _find_column(columns, candidates)
    if chosen in columns:
        return chosen
    hit = _find_column(columns, [chosen])
    if hit is None:
        raise ValueError(f"the CSV log has no {role} column '{chosen}'. Columns found: {list(columns)}")
    return hit


def _read_csv(path: str) -> pd.DataFrame:
    # sep=None detects comma, semicolon, tab, ... (needs the python engine).
    # keep_default_na=False keeps labels such as "nan" or "null" as text;
    # empty cells are removed later.
    return pd.read_csv(
        path,
        sep=None,
        engine="python",
        compression="gzip" if path.lower().endswith(".gz") else None,
        keep_default_na=False,
        dtype=str,
    )


# ---------------------------------------------------------------------------
# TXT
# ---------------------------------------------------------------------------
def _read_text(path: str) -> str:
    if path.lower().endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as handle:
            return handle.read()
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def _text_traces(path: str) -> List[str]:
    """Traces of a TXT log.

    A file in the paper format (first token "!$") is used unchanged. Any other
    TXT file is read as activity tokens separated by "end$" (an optional start
    token "REMEMBERSTART$" is ignored).
    """
    tokens = _read_text(path).split()
    if not tokens or tokens[-1] != END:
        raise ValueError("A TXT log must end every trace with the 'end$' token.")

    paper_format = tokens[0] == START
    traces: List[str] = []
    current: List[str] = []
    for token in tokens:
        if token != END:
            current.append(token)
            continue
        if paper_format:
            if len(current) < 2 or current[0] != START or START in current[1:]:
                raise ValueError("Every trace of a '!$' TXT log must look like: !$ activity$ ... end$")
            bad = [t for t in current[1:] if not _PAPER_TOKEN_RE.match(t) or len(t) > _MAX_LABEL_LENGTH + 1]
            if bad:
                raise ValueError(
                    "In a '!$' TXT log every activity must use only letters, digits, ! or # "
                    f"and end with '$'. Invalid token: {bad[0]!r}."
                )
            traces.append(" ".join([*current, END]))
        else:
            if current and current[0] == "REMEMBERSTART$":
                current = current[1:]
            if not current:
                raise ValueError("The TXT log contains an empty trace.")
            traces.append(_trace_text(current))
        current = []
    return traces


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
def load_traces(
    upload_path: str | Path,
    warnings: Optional[List[str]] = None,
    source_label: Optional[str] = None,
    keys: Optional[LogKeys] = None,
) -> List[str]:
    """Read a log and return its traces ("!$ ... end$" strings) in pipeline order.

    `keys` names the case-id, activity and timestamp attributes (XES) or columns
    (CSV); without it the defaults are used.
    """
    path = str(upload_path)
    name = Path(path).name.lower()
    label = source_label or Path(path).name
    keys = keys or DEFAULT_KEYS

    if name.endswith((".xes", ".xes.gz")):
        try:
            table = _read_xes_table(path, keys)
        except (ET.ParseError, OSError, EOFError) as exc:
            raise ValueError(f"{label}: the XES file could not be read ({exc}).") from exc
        except ValueError as exc:
            raise ValueError(f"{label}: {exc}") from exc
        has_time = table["timestamp"].notna().any()
        traces = _table_to_traces(
            table, "case", "activity", "timestamp" if has_time else None,
            warnings=warnings, source_label=label,
        )
    elif name.endswith((".csv", ".csv.gz")):
        df = _read_csv(path)
        try:
            case_col = _csv_column(df.columns, keys.case, _CASE_CANDIDATES, "case-id")
            act_col = _csv_column(df.columns, keys.activity, _ACTIVITY_CANDIDATES, "activity")
            ts_col = _csv_column(df.columns, keys.timestamp, _TIMESTAMP_CANDIDATES, "timestamp")
        except ValueError as exc:
            raise ValueError(f"{label}: {exc}") from exc
        if not case_col or not act_col:
            raise ValueError(
                f"{label}: a CSV log needs a case-id column and an activity column "
                "(for example case_id, activity, timestamp). Other names can be entered "
                f"under 'Column and attribute names'. Columns found: {list(df.columns)}"
            )
        chosen = [c for c in (case_col, act_col, ts_col) if c]
        if len(set(chosen)) < len(chosen):
            raise ValueError(f"{label}: the case id, the activity and the timestamp must be different columns.")
        if ts_col is None and warnings is not None:
            warnings.append(
                f"{label}: no timestamp column was found, so the row order inside each case was used."
            )
        traces = _table_to_traces(df, case_col, act_col, ts_col, warnings=warnings, source_label=label)
    elif name.endswith((".txt", ".txt.gz")):
        try:
            traces = _text_traces(path)
        except ValueError as exc:
            raise ValueError(f"{label}: {exc}") from exc
    else:
        raise ValueError("Unsupported file type. Use .xes, .xes.gz, .csv, .csv.gz, .txt or .txt.gz.")

    if not traces:
        raise ValueError(f"{label}: no readable traces were found in this log.")
    return traces


def write_traces(traces: Sequence[str], out_path: str | Path) -> Path:
    """Write traces as one line, the way the paper's pipeline does."""
    out = Path(out_path)
    out.write_text(" ".join(traces), encoding="ascii")
    return out


def activities_of(trace: str) -> List[str]:
    """Activity tokens of one "!$ ... end$" trace string (without !$ and end$)."""
    return trace.split()[1:-1]
