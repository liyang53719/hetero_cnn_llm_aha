#!/bin/sh
# Cold/static only. Does not launch a numerical worker or generate RTL.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=${1:-.}
python -B -I "$HERE/test_gate.py" --source-root "$ROOT" -v
python -B -I -O "$HERE/test_gate.py" --source-root "$ROOT" -v
python -B -I "$HERE/test_elf_closure.py" -v
