#!/usr/bin/env python3
"""Fresh raw-input Q8/K2 vectors: cold tokens0..15 and carried tokens112..127.

Outputs live only in ignored work/. Native failures are reported without
changing thresholds or substituting captured projection values. This command
does not run RTL or certify the full native block.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.matrix_norm_rope_tile16_candidate import materialize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--payload-layer0', type=Path, default=ROOT / 'work/qwen35_layer0_payload')
    parser.add_argument('--payload-layer3', type=Path, default=ROOT / 'work/qwen35_layer3_payload')
    parser.add_argument('--payload-extra', type=Path, default=ROOT / 'work/qwen35_prefix_payload')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = materialize(args.root, args.payload_layer0, args.payload_layer3, args.payload_extra, args.output)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as exc:
        print('MATRIX_NORM_ROPE_TILE16_MATERIALIZATION_REJECTED: ' + str(exc), file=sys.stderr)
        raise SystemExit(3)
    print(json.dumps({name: result[name] for name in
        ('status', 'summary_sha256', 'cases_per_variant', 'commands_per_variant', 'variants',
         'totals', 'native_gate_pass', 'native_failed_comparisons',
         'native_failed_command_comparisons', 'native_full_block_gate_pass',
         'supplemental_cases_per_variant', 'supplemental_totals',
         'supplemental_native_gate_pass', 'supplemental_native_failed_comparisons')}, indent=2))


if __name__ == '__main__':
    main()
