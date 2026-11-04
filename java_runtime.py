# SPDX-FileCopyrightText: 2026 Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GNU GPL v3, section 7): see the file NOTICE.
"""
java_runtime.py - find a Java 17+ runtime for the engine (standard library only).

Search order: JAVA_HOME, the macOS Java registry (/usr/libexec/java_home),
the "java" command on PATH, then common installation folders on Windows,
macOS (including Homebrew) and Linux.

Run this file directly to check a computer:

    python3 java_runtime.py
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

MIN_JAVA = 17
INSTALL_HINT = "Install Java 17 or newer (for example Temurin 21 LTS from https://adoptium.net)."


class JavaNotFound(RuntimeError):
    """Raised when no Java 17+ runtime can be found."""


def _exe(bin_folder: str | Path) -> Path:
    return Path(bin_folder) / ("java.exe" if os.name == "nt" else "java")


def _candidates() -> Iterator[Path]:
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        yield _exe(Path(java_home) / "bin")

    if sys.platform == "darwin":
        # On macOS /usr/bin/java is only a launcher stub; ask the system for a
        # real JDK/JRE instead.
        try:
            proc = subprocess.run(
                ["/usr/libexec/java_home", "-v", f"{MIN_JAVA}+"],
                capture_output=True, text=True, timeout=15, check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                yield _exe(Path(proc.stdout.strip()) / "bin")
        except (OSError, subprocess.SubprocessError):
            pass

    on_path = shutil.which("java")
    if on_path and not (sys.platform == "darwin" and on_path == "/usr/bin/java"):
        yield Path(on_path)

    patterns: List[str] = []
    if os.name == "nt":
        bases = [os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")]
        if os.environ.get("LOCALAPPDATA"):
            bases.append(os.path.join(os.environ["LOCALAPPDATA"], "Programs"))
        vendors = ["Eclipse Adoptium", "Java", "Microsoft", "Zulu", "Amazon Corretto", "BellSoft", "OpenJDK"]
        patterns += [os.path.join(b, v, "*", "bin") for b in bases if b for v in vendors]
    elif sys.platform == "darwin":
        patterns += [
            "/Library/Java/JavaVirtualMachines/*/Contents/Home/bin",
            os.path.expanduser("~/Library/Java/JavaVirtualMachines/*/Contents/Home/bin"),
            "/opt/homebrew/opt/openjdk*/bin",   # Homebrew, Apple silicon
            "/usr/local/opt/openjdk*/bin",      # Homebrew, Intel
        ]
    else:
        patterns.append("/usr/lib/jvm/*/bin")
    patterns.append(os.path.expanduser("~/.sdkman/candidates/java/*/bin"))

    for pattern in patterns:
        for folder in sorted(glob.glob(pattern), reverse=True):
            yield _exe(folder)


def java_version(java: str | Path) -> Optional[int]:
    """Return the major version of a Java executable, or None if it does not run."""
    try:
        proc = subprocess.run(
            [str(java), "-version"], capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    match = re.search(r'version\s+"(\d+)(?:\.(\d+))?', f"{proc.stdout}\n{proc.stderr}")
    if not match:
        return None
    major = int(match.group(1))
    if major == 1 and match.group(2):  # old style, e.g. "1.8.0_392" -> 8
        major = int(match.group(2))
    return major


@lru_cache(maxsize=1)
def find_java() -> Tuple[str, int]:
    """Return (path to java, major version) of the first Java 17+ found."""
    seen = set()
    too_old: List[str] = []
    for exe in _candidates():
        if not exe.is_file():
            continue
        try:
            key = exe.resolve()
        except OSError:
            key = exe
        if key in seen:
            continue
        seen.add(key)
        version = java_version(exe)
        if version is None:
            continue
        if version >= MIN_JAVA:
            return str(exe), version
        too_old.append(f"Java {version} at {exe}")

    message = f"Java {MIN_JAVA} or newer was not found."
    if too_old:
        message += " Only older versions were found: " + "; ".join(too_old) + "."
    raise JavaNotFound(f"{message} {INSTALL_HINT}")


if __name__ == "__main__":
    try:
        path, version = find_java()
    except JavaNotFound as exc:
        print(f"[REMEMBER] ERROR: {exc}")
        sys.exit(1)
    print(f"[REMEMBER] Java {version} found: {path}")
