#!/usr/bin/env python3
"""Generate transient real-prefix Matrix -> Norm256 -> partial64 RoPE vectors.

Always executes pinned baseline/AVX2 official prefixes and native captures.
No downloaded NPZ, replayed projected input, or arbitrary saved-manifest path
is accepted. Outputs, checkpoint slices and rebuildable arrays stay in work/.
Native diagnostic failures are disclosed, independently of exact oracle/C
agreement; this command does not execute RTL or certify the native block.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.matrix_norm_rope_candidate import materialize


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
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as exc:
        print('MATRIX_NORM_ROPE_MATERIALIZATION_REJECTED: ' + str(exc), file=sys.stderr)
        raise SystemExit(3)
    print(json.dumps({name: result[name] for name in
                      ('status', 'summary_sha256', 'cases_per_variant', 'variants',
                       'native_gate_pass', 'native_failed_comparisons', 'native_full_block_gate_pass')}, indent=2))


if __name__ == '__main__':
    main()
