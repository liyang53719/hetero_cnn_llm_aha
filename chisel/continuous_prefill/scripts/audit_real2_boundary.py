#!/usr/bin/env python3
"""Read-only cross-run and actual-predecessor audit for the synthetic real16 gate.

This complements verify_real_two_layer.py. It is not an RTL simulation and does
not prove an official checkpoint's model quality. The RMS recipe below is an
independent array implementation of the frozen synthetic BF16/FP32 contract.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

TOKENS, HIDDEN, FFN, KV = 16, 1536, 8960, 256
PEER_SOURCE = '6d39c76aa1420cb42564c530860f6c32cd8cc41d'
WORDS = {name: TOKENS * width for name, width in [
    ('n0',HIDDEN),('qraw',HIDDEN),('qr',HIDDEN),('q',HIDDEN),
    ('kraw',KV),('kr',KV),('k',KV),('vraw',KV),('v',KV),
    ('cache_k',KV),('cache_v',KV),('att',HIDDEN),('o',HIDDEN),
    ('r',HIDDEN),('n1',HIDDEN),('gate',FFN),('up',FFN),
    ('act',FFN),('down',HIDDEN),('y',HIDDEN)]}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def read_tensor(root: Path, name: str, words: int) -> bytes:
    path = root / 'tensors' / name
    require(path.is_file() and not path.is_symlink(), 'missing/symlink tensor: '+name)
    raw = path.read_bytes()
    require(len(raw) == words * 4, 'wrong tensor byte count: '+name)
    require(bool(np.isfinite(np.frombuffer(raw, dtype='<f4')).all()), 'nonfinite tensor: '+name)
    return raw


def bf16_rne(x: np.ndarray) -> np.ndarray:
    a = np.asarray(x, dtype='<f4')
    require(bool(np.isfinite(a).all()), 'nonfinite BF16 input')
    u = a.view('<u4')
    rounded = (u + np.uint32(0x7fff) + ((u >> 16) & 1)) & np.uint32(0xffff0000)
    result = rounded.view('<f4')
    require(bool(np.isfinite(result).all()), 'BF16 overflow')
    return result


def ordered_input_norm(raw: bytes) -> bytes:
    require(len(raw) == TOKENS * HIDDEN * 4, 'wrong hidden tensor length')
    x = np.frombuffer(raw, dtype='<f4').reshape(TOKENS,HIDDEN)
    require(bool(np.isfinite(x).all()), 'nonfinite hidden tensor')
    # Keep each row's original increasing-column FP32 accumulation order.
    accum = np.zeros(TOKENS, dtype=np.float32)
    for col in range(HIDDEN):
        accum = np.add(accum, np.multiply(x[:,col], x[:,col], dtype=np.float32), dtype=np.float32)
    variance = np.add(np.multiply(accum, np.float32(1.0/HIDDEN), dtype=np.float32), np.float32(1e-6), dtype=np.float32)
    inverse = np.divide(np.float32(1.0), np.sqrt(variance, dtype=np.float32), dtype=np.float32)
    gamma = bf16_rne(np.add(np.float32(0.9), np.multiply(np.arange(HIDDEN,dtype=np.int32)%11,np.float32(0.015625),dtype=np.float32),dtype=np.float32))
    normalized = np.multiply(np.multiply(x,inverse[:,None],dtype=np.float32),gamma,dtype=np.float32)
    return bf16_rne(normalized).tobytes()


def audit(evidence: Path, peer: Path) -> dict:
    for root in (evidence,peer):
        require((root/'simulation.exit').read_text().strip() == '0', 'simulation not successful')
        require((root/'gate.exit').read_text().strip() == '0', 'gate not complete')
    require((peer/'source_base_commit.txt').read_text().strip() == PEER_SOURCE, 'wrong frozen peer source')
    m = json.loads((evidence/'fixture/manifest.json').read_text())
    require((m['tokens'],m.get('layers'),m['shape']['H'],m['shape']['F']) == (TOKENS,2,HIDDEN,FFN), 'wrong fixed geometry')
    require(m['tensors']['l1_x']['address'] == m['tensors']['l0_y']['address'], 'layer boundary address is not an alias')
    require(m['tensors']['l1_x']['readonly'] is False and 'l1_x' not in m['allocations'], 'Host input allocated for layer one')
    initial = read_tensor(evidence,'input_x.f32le',TOKENS*HIDDEN)
    require(initial == read_tensor(peer,'input_x.f32le',TOKENS*HIDDEN), 'different peer stimulus')
    checked, hashes = 0, {}
    for name, words in WORDS.items():
        raw = read_tensor(evidence,'l0_'+name+'_actual.f32le',words)
        require(raw == read_tensor(peer,name+'_actual.f32le',words), 'first-layer cross-run drift: '+name)
        hashes[name] = hashlib.sha256(raw).hexdigest(); checked += words
    require(checked == 704512, 'incomplete frozen-peer comparison')
    producer = read_tensor(evidence,'l0_y_actual.f32le',TOKENS*HIDDEN)
    consumer = read_tensor(evidence,'l1_n0_actual.f32le',TOKENS*HIDDEN)
    expected = ordered_input_norm(producer)
    require(consumer == expected, 'second-layer InputNorm does not match actual previous Y')
    require(consumer != ordered_input_norm(initial), 'second-layer norm reused original X')
    return {'schema':1,'status':'PASS_REAL2_FROZEN_PEER_AND_ACTUAL_BOUNDARY',
            'peer_source':PEER_SOURCE,'peer_compared_fp32':checked,
            'boundary_norm_recomputed_fp32':TOKENS*HIDDEN,'bit_differences':0,
            'first_layer_actual_sha256':hashes,
            'producer_y_sha256':hashlib.sha256(producer).hexdigest(),
            'consumer_n0_sha256':hashlib.sha256(consumer).hexdigest(),
            'rtl_rerun':False,'reference_tensors_used_for_boundary':False,
            'scope':'Synthetic real16 two-layer contract; supplements full 42-command numeric/ABI verification.'}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,required=True);p.add_argument('--peer',type=Path,required=True)
    p.add_argument('--output',type=Path);a=p.parse_args()
    try:
        if a.output:require(not a.output.exists(),'refuse to overwrite audit')
        result=audit(a.evidence,a.peer);text=json.dumps(result,indent=2)+'\n'
        if a.output:
            with a.output.open('x') as f:f.write(text)
        print(text,end='')
    except (ValueError,OSError,KeyError,TypeError) as e:
        raise SystemExit('REAL2_BOUNDARY_REJECTED: '+str(e))
