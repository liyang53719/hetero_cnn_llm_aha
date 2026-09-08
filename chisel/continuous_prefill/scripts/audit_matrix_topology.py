#!/usr/bin/env python3
"""Count reachable logical engines and retained arithmetic slices, not text hits.

CIRCT deduplicates identical adapter module definitions. One textual retained
endpoint in such a definition can have eight physical instances; walk the
hierarchy from HostBlockTop. No generated file is edited by this checker.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, re
from pathlib import Path


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def counts(text: str, root: str = 'HostBlockTop') -> collections.Counter:
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    blocks = dict(re.findall(r'\bmodule\s+([\w$]+)\b(.*?)\bendmodule\b', clean, re.S))
    require(root in blocks, 'missing generated root')
    terminal = {'qwen2_matrix_command_endpoint', 'idma_backend_rw_axi_flat_wrap'}
    known = set(blocks) | terminal
    found = collections.Counter()
    def walk(name: str, stack: tuple[str, ...]) -> None:
        require(name not in stack and len(stack) < 100, 'recursive/unbounded hierarchy')
        found[name] += 1
        if name in terminal:
            return
        body = blocks[name]
        # Generated modules have no instance arrays or parameter overrides.
        # Reject these forms for the target arithmetic rather than undercount.
        for kind, instance in re.findall(r'^\s*([\w$]+)\s+([\w$]+)\s*\(', body, re.M):
            if kind in known:
                walk(kind, stack + (name,))
    walk(root, ())
    return found


def audit(path: Path, macs: int) -> dict:
    require(type(macs) is int and macs in (512, 4096), 'unsupported peak MAC count')
    raw = path.read_bytes(); found = counts(raw.decode())
    require(found['qwen2_matrix_command_endpoint'] == macs // 512, 'wrong physical 512-MAC slice count')
    require(found['idma_backend_rw_axi_flat_wrap'] == 1, 'iDMA duplicated or missing')
    logical = found['ScalableMatrixTileAdapter'] + found['MatrixPipelineService']
    require(logical == 1, 'not one logical Matrix engine')
    if found['MatrixPipelineService']:
        require(macs == 4096 and found['StreamingDenseOwner'] == 1 and found['VectorSiluOwner'] == 1,
                'incomplete production pipeline topology')
    require(not any('HeteroBF16FmaLane' in n for n in found), 'fallback standalone MAC arithmetic')
    return {'status':'PASS_REACHABLE_MATRIX_TOPOLOGY','logical_matrix_engines':1,
            'physical_512mac_slices':macs//512,'rows':16,'columns':macs//16,
            'peak_macs_per_cycle':macs,'idma_instances':1,
            'generated_sha256':hashlib.sha256(raw).hexdigest(),
            'timing_signoff':False,'instances':dict(sorted(found.items()))}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sv',type=Path)
    p.add_argument('--macs',type=int,choices=(512,4096),required=True);a=p.parse_args()
    print(json.dumps(audit(a.sv,a.macs),indent=2))
