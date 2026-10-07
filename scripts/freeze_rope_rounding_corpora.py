#!/usr/bin/env python3
"""Extract immutable subsets from historical native/RTL evidence, never rerun CPU.

Required source bytes are pinned below. The compact output preserves native
products/output and both actual hardware results, rather than deriving expected
values from the new ablation. Optional reproduction needs the original evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from heteronpu.model_geometry import require

PINS = {
 'local': {'audit_report': 'fece52d072ea997675a59865ed1e5ffb48ac28e41b7ae3e8e32552f8e9d0fda1',
           'audit_arrays': '836ce634c677f5b171c69c525a8d5cf6d018b30414f06427c236c8c08803bff7',
           'component_report': '42457029cd3abd9fe9a44ecbebb6ba43bed1c539078eb238123d0d177a21545a'},
 'remote': {'audit_report': 'd04f72678b8347bcf872f5a33c5948a0fc66e14a4f98d1a60d0976a611523d25',
            'audit_arrays': '81f51be898714b17602eaa63e51d945c7a7552cf0e0e25648fbe863948f4fe48',
            'component_report': '73ce7a2336901b30b9fdaaf8f5c05098bf409a2d96252b93ff20aab382887608'}
}

def record(path):
    return {'file':path.name, 'bytes':path.stat().st_size, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def extract(label, audit, component, output):
    pin = PINS[label]
    require(record(audit/'result.json')['sha256'] == pin['audit_report'], 'historical audit report drift')
    require(record(audit/'all_bf16_producers.npz')['sha256'] == pin['audit_arrays'], 'historical audit bytes drift')
    require(record(component/'result.json')['sha256'] == pin['component_report'], 'historical RTL report drift')
    ar = json.loads((audit/'result.json').read_text())
    cr = json.loads((component/'result.json').read_text())
    require(ar['arrays'] == record(audit/'all_bf16_producers.npz') == cr['native_audit_arrays'], 'native provenance mismatch')
    require(cr['vectors'] == record(component/'oracle_vectors.npy'), 'historical vector drift')
    require(cr['real_QK_pairs'] == 81920 and len(cr['rtl_runs']) == 2, 'historical corpus scope drift')
    vectors = np.load(component/'oracle_vectors.npy', allow_pickle=False)
    hw = []
    for i, run in enumerate(cr['rtl_runs']):
        path = component/f'rtl_outputs{i}.txt'
        require(record(path) == run['outputs'], 'actual RTL text drift')
        words = np.array([[int(v,16) for v in row.split()] for row in path.read_text().splitlines()], dtype=np.uint32)
        require(np.array_equal(words, vectors[:,4:]), 'historical RTL mismatch')
        require(np.array_equal(words, np.load(component/f'rtl_outputs{i}.npy',allow_pickle=False)), 'RTL NPY/text mismatch')
        hw.append(words[:81920])
    inputs, products, native, groups = [], [], [], []
    with np.load(audit/'all_bf16_producers.npz', allow_pickle=False) as arrays:
        for case in ('cold_m128','carried_m128'):
            cos = arrays[f'{case}_native_cos'].view(np.uint32)
            sin = arrays[f'{case}_native_sin'].view(np.uint32)
            require(cos.shape == sin.shape == (1,128,64), 'coefficient shape')
            require(np.array_equal(cos[...,:32],cos[...,32:]) and np.array_equal(sin[...,:32],sin[...,32:]),'coefficient half drift')
            for label2, index, heads, product in (('q',16,8,27),('k',25,2,30)):
                x=arrays[f'{case}_native_producer_{index:02}'].view(np.uint32)
                prods=[arrays[f'{case}_native_producer_{p:02}'].view(np.uint32).transpose(0,2,1,3) for p in (product,product+1,product+2)]
                require(x.shape==(1,128,heads,256) and all(p.shape==(1,128,heads,64) for p in prods), 'producer shape')
                start=len(inputs)
                for t in range(128):
                    for h in range(heads):
                        for ch in range(32):
                            inputs.append((x[0,t,h,ch],x[0,t,h,ch+32],cos[0,t,ch],sin[0,t,ch]))
                            # ec, os, es, oc, with os signed like actual positive-odd product.
                            products.append((prods[0][0,t,h,ch],prods[1][0,t,h,ch]^0x80000000,prods[1][0,t,h,ch+32],prods[0][0,t,h,ch+32]))
                            native.append((prods[2][0,t,h,ch],prods[2][0,t,h,ch+32]))
                groups.append({'case':case,'producer':label2,'heads':heads,'start':start,'pairs':len(inputs)-start})
    data={'inputs':np.array(inputs,dtype=np.uint32),'native_products':np.array(products,dtype=np.uint32),
          'native_outputs':np.array(native,dtype=np.uint32),'hardware_comb':hw[0],'hardware_pipe':hw[1]}
    require(np.array_equal(data['inputs'],vectors[:81920,:4]),'native to historical RTL input binding mismatch')
    for value in (data['inputs'],data['native_products'],data['native_outputs']):
        require(not np.any(value & 0xffff), 'non-BF16 frozen input')
    output.mkdir(parents=True,exist_ok=True)
    target=output/f'{label}.npz'
    np.savez_compressed(target,**data)
    return {'bundle':record(target),'groups':groups,'original_audit_report':record(audit/'result.json'),
            'original_audit_arrays':ar['arrays'],'original_component_report':record(component/'result.json'),
            'original_vectors':cr['vectors'],'original_actual_RTL_outputs':[r['outputs'] for r in cr['rtl_runs']],
            'model_id':ar['model_id'],'revision':ar['revision'],'framework_revision':ar['framework_revision'],
            'historical_native_audit_status':ar['status'],'historical_native_failed_comparisons':len(ar['failed_producers']),
            'environment':ar['environment'],'arithmetic_recomputed_when_freezing':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('local-audit','local-component','remote-audit','remote-component','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    metadata={k:extract(k,getattr(a,k+'_audit'),getattr(a,k+'_component'),a.output) for k in PINS}
    # Historical synthetic cases are copied as input bits, never model data.
    old=np.load(a.local_component/'oracle_vectors.npy',allow_pickle=False)
    np.save(a.output/'historical_arithmetic.npy',old[81920:,:4].copy(),allow_pickle=False)
    (a.output/'provenance.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(metadata,indent=2))
