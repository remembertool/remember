#!/bin/bash
# SPDX-FileCopyrightText: 2026 Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GNU GPL v3, section 7): see the file NOTICE.
# macOS: double-click this file in Finder to start REMEMBER.
# If macOS blocks it, open Terminal, type "bash " (with a space), drag this
# file into the Terminal window and press Enter. See README.md.
cd "$(dirname "$0")" || exit 1
exec /bin/bash ./run_unix.sh
