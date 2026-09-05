#!/usr/bin/env bash
set -eu
# Print a display label whose hash belongs to a quoted string.
printf '%s\n' 'sensor #1'
# Keep the multi-line quoted record intact while printing it.
printf '%s\n' 'Shell record
# This line is string data, not a shell comment.
End of record'
# Run the scientific summary from the current project directory.
python3 analysis.py
