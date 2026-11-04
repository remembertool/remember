#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GNU GPL v3, section 7): see the file NOTICE.
# REMEMBER launcher for macOS and Linux (macOS users can double-click run_mac.command).
# First start: creates a private Python environment (.venv) and installs the
# packages from requirements.txt. This needs internet once.

cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"

say() { printf '[REMEMBER] %s\n' "$*"; }
fail() {
  printf '[REMEMBER] ERROR: %s\n' "$*" >&2
  if [ -t 0 ]; then
    printf 'Press Enter to close this window.'
    read -r _
  fi
  exit 1
}

# 1. Python 3.11 or newer --------------------------------------------------
is_macos=0
[ "$(uname -s)" = "Darwin" ] && is_macos=1

PY=""
for candidate in python3 python3.14 python3.13 python3.12 python3.11 python \
                 /opt/homebrew/bin/python3 /usr/local/bin/python3 \
                 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  exe="$(command -v "$candidate" 2>/dev/null)" || continue
  # On macOS, /usr/bin/python3 is only a stub until Apple's developer tools are
  # installed (and then it is Python 3.9). Do not trigger the install dialog.
  if [ "$is_macos" = 1 ] && [ "$exe" = "/usr/bin/python3" ] && ! xcode-select -p >/dev/null 2>&1; then
    continue
  fi
  if "$exe" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    PY="$exe"
    break
  fi
done
[ -n "$PY" ] || fail "Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/ and start REMEMBER again."
say "Python: $("$PY" -c 'import sys; print(sys.version.split()[0])') ($PY)"

# 2. Java 17 or newer and the engine files -----------------------------------
for jar in jfitVlmc-paper.jar trace2ecf-paper.jar; do
  [ -f "$ROOT/engine/$jar" ] || fail "engine/$jar is missing. Please use a complete copy of the package."
done
"$PY" "$ROOT/java_runtime.py" || fail "Java 17 or newer is required (see the message above)."

# 3. Private Python environment (.venv) --------------------------------------
VENV_PY="$ROOT/.venv/bin/python"
if [ -e "$ROOT/.venv" ] && ! "$VENV_PY" -c 'import sys' >/dev/null 2>&1; then
  say "The .venv folder does not work any more (Python was updated or the folder was moved). Creating it again ..."
  rm -rf "$ROOT/.venv"
fi
if [ ! -e "$ROOT/.venv" ]; then
  say "First start: creating the Python environment (.venv) ..."
  if ! "$PY" -m venv "$ROOT/.venv"; then
    rm -rf "$ROOT/.venv"
    fail "Could not create .venv. On Ubuntu/Debian, install the venv module first: sudo apt install python3-venv"
  fi
fi

STAMP="$ROOT/.venv/requirements.installed"
if ! cmp -s "$ROOT/requirements.txt" "$STAMP"; then
  say "Installing the Python packages (only the first time; this can take a few minutes) ..."
  "$VENV_PY" -m pip install --disable-pip-version-check --only-binary=:all: -r "$ROOT/requirements.txt" \
    || fail "Package installation failed. Check the internet connection. If your Python is very new, install Python 3.13 from https://www.python.org/downloads/ and try again."
  cp "$ROOT/requirements.txt" "$STAMP"
fi

# 4. Start ------------------------------------------------------------------
REMEMBER_OPEN_BROWSER=1 "$VENV_PY" "$ROOT/app.py"
status=$?
if [ "$status" -ne 0 ] && [ "$status" -ne 130 ]; then
  fail "REMEMBER stopped with an error (code $status). Please read the messages above."
fi
