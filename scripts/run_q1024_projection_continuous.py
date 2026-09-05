#!/usr/bin/env python3
"""Automatically advance verified segments; no polling, retries or gate relaxation."""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--projection',type=int,choices=(0,1,2),required=True)
    args=parser.parse_args()
    directory=ROOT/f'work/results/q1024_continuous/p{args.projection}'
    directory.mkdir(parents=True,exist_ok=True)
    owner=(directory.parent/'coordinator.lock').open('a')
    fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
    while True:
        # Block on the real controller lock until any current segment has exited
        # AND written its receipt. No timed polling or duplicate launches.
        with (directory.parent/'controller.lock').open('a') as controller:
            fcntl.flock(controller,fcntl.LOCK_EX)
            paths=sorted(directory.glob('segment_[0-9][0-9][0-9].json'))
            if paths:
                receipt=json.loads(paths[-1].read_text())
                assert receipt['projection']==args.projection
                assert receipt['segment']==len(paths)-1, 'noncontiguous receipts'
                if receipt['status']=='PROJECTION_NUMERICAL_COMPLETE':
                    break
                if receipt['status']!='CHECKPOINT':
                    raise SystemExit(f"STOP: inspect {paths[-1]} ({receipt['status']}); no automatic restart")
            segment=len(paths)
        print(f'CONTINUOUS_START projection={args.projection} segment={segment}',flush=True)
        subprocess.run([sys.executable,str(ROOT/'scripts/run_q1024_projection_segment.py'),
                        '--projection',str(args.projection),'--segment',str(segment)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/collect_q1024_projection_chain.py'),
                    '--projection',str(args.projection)],cwd=ROOT,check=True)
    print(f'CONTINUOUS_PROJECTION_COMPLETE projection={args.projection} full_model_complete=false',flush=True)


if __name__=='__main__': main()
