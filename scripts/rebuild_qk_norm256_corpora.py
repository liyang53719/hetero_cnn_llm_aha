#!/usr/bin/env python3
"""Rebuild fresh baseline/AVX2 QK corpora from verified official checkpoint slices.

Use the pinned Torch/NumPy/Transformers runtime. Outputs belong under work/.
Historical local.npz/remote.npz are never reconstructed, renamed or overwritten.
A saved manifest is not a reusable CLI trust anchor; the candidate runner calls
rebuild() and retains its digest within the same invocation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.qk_norm256_materialization import rebuild, run_variant


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--payload-layer0', type=Path, required=True)
    parser.add_argument('--payload-layer3', type=Path, required=True)
    parser.add_argument('--payload-extra', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--_variant', choices=('baseline', 'avx2'), help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        inputs = (args.root, args.payload_layer0, args.payload_layer3, args.payload_extra, args.output)
        if args._variant:
            run_variant(*inputs, args._variant)
            return
        corpora, digest = rebuild(*inputs)
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as exc:
        print('QK_MATERIALIZATION_REJECTED: ' + str(exc), file=sys.stderr)
        raise SystemExit(3)
    print(json.dumps({'status': 'FRESH_OFFICIAL_QK_CORPORA_MATERIALIZED',
        'manifest_sha256': digest, 'output': str(args.output),
        'heads': sum(len(data['role']) for data, origin in corpora.values()),
        'variants': list(corpora), 'historical_byte_identity_claimed': False,
        'unique_input_count_claimed': False}, indent=2))


if __name__ == '__main__':
    main()
