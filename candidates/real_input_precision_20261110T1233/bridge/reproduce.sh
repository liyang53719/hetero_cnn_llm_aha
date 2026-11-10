#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
B=round_20261110T1233/bridge
D=published_source_closure_recovery_20261029T1833/candidates/host_runtime_non_dpi_backend/source
sha256sum -c "$B/DEPENDENCY_PINS.txt"
g++ -O2 -fno-fast-math "$B/rope_input.cpp" -o "$B/rope_input"
"$B/rope_input" "$B/rope.f32le"
g++ -O2 -std=c++17 -I "$D" "$B/config_probe.cpp" -lcrypto -o "$B/config_probe"
python "$B/test_bridge.py"
# For persistent local manifests choose a NEW directory, preserving prior evidence:
# python "$B/adapt.py" --payload round_20261110T0733/qwen2_host_payload --rope "$B/rope.f32le" --output "$B/local_payload_NEW"
