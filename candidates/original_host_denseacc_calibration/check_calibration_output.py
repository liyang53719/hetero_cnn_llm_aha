#!/usr/bin/env python3
"""Check the exact finite-miter text contract; this parser never runs a DUT."""
from pathlib import Path
import argparse, hashlib, json
EXPECTED = (
    'DENSEACC_CALIBRATION_SCOPE actual-original-AST_vs-actual-transformed-AST; full4096; no-Host-control-or-block-qualification\n'
    'DENSEACC_CALIBRATION_COUNTS clocked_cycles=17 scans=49 row_domain=32 beat_domain=16 words_per_read=16 write_masks=8 pair_checks=401408 witness_checks=401408 alias_checks=200704\n'
    'DENSEACC_CALIBRATION_INITIALIZATION fixed-two-state-randReset0-only; original-unreset-storage; no-hardware-zero-init-claim\n'
    'COMPLETE_DENSEACC_ACTUAL_STORAGE_EQUIVALENCE_CALIBRATION_NOT_HOST_NUMERIC_OR_PROVIDER_RTL\n'
).encode('ascii')

def check(data):
    if data != EXPECTED:
        raise ValueError('Exact four-line finite-calibration contract required')
    return {'status': 'OUTPUT_CONTRACT_MATCH_ONLY_NOT_INDEPENDENT_DUT_PROOF',
            'clocked_cycles': 17, 'scans': 49, 'pair_checks': 401408,
            'witness_checks': 401408, 'alias_checks': 200704,
            'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    if args.log.is_symlink() or args.log.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Bounded regular log required')
    print(json.dumps(check(args.log.read_bytes()), sort_keys=True))

if __name__ == '__main__':
    main()
