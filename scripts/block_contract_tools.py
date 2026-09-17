#!/usr/bin/env python3
"""Independent control/receipt/weight tools; none executes a model or RTL."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import random
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from heteronpu.command_window_contract import compile_program,chain_program,WindowMachine
from heteronpu.block_receipt import read_json,verify
from heteronpu.weight_packing import PackContract,pack_file,verify_package


def control_case(count: int, seed: int) -> dict:
    spec=compile_program(chain_program(count));d=WindowMachine(spec);d.start(1)
    rng=random.Random(seed);offers=acks=retired=stalls=0
    while d.state!='done':
        if d.state=='fetch':
            d.accept_window(*d.window_request())
        elif d.state=='offer':
            held=d.offer();ready=rng.randrange(4)!=0
            if ready:
                if d.issue(True)!=held: raise ValueError('unstable offer')
                offers+=1
            else:
                d.issue(False);stalls+=1
                if d.offer()!=held: raise ValueError('stalled offer changed')
        elif d.state=='wait_ack':
            if rng.randrange(4)==0: stalls+=1;continue
            d.acknowledge(d.epoch,d.pc,d.held.size);acks+=1
        elif d.state=='completion':
            if rng.randrange(4)==0: d.retire(False);stalls+=1;continue
            d.retire(True);retired+=1
        else: raise ValueError('unexpected control state')
    if not offers==acks==retired==count: raise ValueError('lost command')
    return dict(commands=count,seed=seed,windows=len(spec.windows),peak_live=spec.peak_live,
                issued=offers,acknowledged=acks,completed=retired,write_ack_bytes=d.acked_bytes,
                injected_wait_events=stalls,rtl_execution=False,cycle_performance_claimed=False)


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    ctrl=sub.add_parser('control');ctrl.add_argument('--count',type=int,default=588);ctrl.add_argument('--seed',type=int,default=1)
    rec=sub.add_parser('receipt');rec.add_argument('root',type=Path);rec.add_argument('manifest',type=Path);rec.add_argument('receipt',type=Path)
    for cmd in ('pack','readback'):
        a=sub.add_parser(cmd);a.add_argument('source',type=Path);a.add_argument('package',type=Path);a.add_argument('contract',type=Path)
    args=p.parse_args()
    try:
        if args.action=='control': result=control_case(args.count,args.seed)
        elif args.action=='receipt': result=verify(args.manifest,args.receipt,args.root)
        else:
            contract=PackContract(**read_json(args.contract))
            if args.action=='pack': pack_file(args.source,args.package,contract)
            result=verify_package(args.source,args.package,contract)
        print(json.dumps(result,indent=2));return 0
    except (ValueError,TypeError,KeyError,OSError) as exc:
        print('CONTRACT_REJECTED: '+str(exc),file=sys.stderr);return 2


if __name__=='__main__': raise SystemExit(main())
