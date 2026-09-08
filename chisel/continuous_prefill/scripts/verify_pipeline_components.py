#!/usr/bin/env python3
"""Independently check actual production-pipeline simulation outputs, read-only.

The fixed finite stimuli permit exact binary64 products and sums before the
specified FP32 rounding. This is not a general IEEE FMA implementation, an RTL
simulator, an official-model quality reference, or a physical timing signoff.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from audit_matrix_topology import counts


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def array(path: Path, words: int) -> np.ndarray:
    require(path.is_file() and not path.is_symlink(), 'missing/symlink output: ' + str(path))
    raw = path.read_bytes()
    require(len(raw) == words * 4, 'incomplete output: ' + str(path))
    x = np.frombuffer(raw, dtype='<f4')
    require(bool(np.isfinite(x).all()), 'nonfinite output: ' + str(path))
    return x


def bf16(x: np.ndarray) -> np.ndarray:
    u = np.asarray(x, dtype='<f4').view('<u4')
    return ((u + np.uint32(0x7fff) + ((u >> 16) & 1)) & np.uint32(0xffff0000)).view('<f4')


def pipeline_values(mask: int, contexts: int, depth: int) -> np.ndarray:
    acc = np.zeros((contexts,16,256), dtype='<f4'); output = []
    rows, cols = np.arange(16)[:,None], np.arange(256)[None,:]
    selected = ((mask >> (cols // 32)) & 1).astype(bool)
    for k in range(depth):
        for context in range(contexts):
            a = ((k + context*3 + rows) % 31 - 15).astype(np.float64) / 32
            b = ((k*7 + context*13 + cols) % 61 - 30).astype(np.float64) / 64
            summed = (a*b + acc[context].astype(np.float64)).astype('<f4')
            acc[context] = np.where(selected, summed, acc[context])
            output.append(acc[context].copy().reshape(-1))
    return np.concatenate(output)


DENSE_CASES = [(16,1536,64,1), (17,528,128,2), (1,16,16,3),
               (16,1280,32,4), (16,1536,64,6), (16,528,32,8)]


def dense_values(m: int,n: int,k: int,seed: int) -> np.ndarray:
    i,j = np.arange(m*k,dtype=np.int64), np.arange(k*n,dtype=np.int64)
    a = np.multiply(((i*13+seed)%127-63).astype('<f4'),np.float32(0.03131),dtype=np.float32).reshape(m,k)
    b = np.multiply(((j*17+seed*7)%61-30).astype('<f4'),np.float32(0.007821),dtype=np.float32).reshape(k,n)
    a,b = bf16(a).astype(np.float64),bf16(b).astype(np.float64)
    c = np.zeros((m,n),dtype='<f4')
    for z in range(k):
        c = (a[:,z,None]*b[z,None,:] + c.astype(np.float64)).astype('<f4')
    return c.reshape(-1)


def check_outputs(folder: Path,expected: np.ndarray) -> dict:
    require((folder/'simulation.exit').read_text().strip() == '0', 'simulator failed')
    log = (folder/'run.log').read_text()
    require(re.search(r'MATRIX_PIPELINE_FAIL:|STREAM_DENSE_FAIL:|PIPELINE_FAILURE_GATE_FAIL:|%Error|\bFatal\b|Segmentation fault',log) is None, 'failed DUT log')
    words = int(expected.size)
    actual = array(folder/'outputs/actual.f32le',words)
    reference = array(folder/'outputs/reference.f32le',words)
    require(np.array_equal(actual.view('<u4'),expected.view('<u4')), 'actual differs from independent arithmetic')
    require(np.array_equal(reference.view('<u4'),expected.view('<u4')), 'C++ oracle differs from independent arithmetic')
    return {'checked_fp32':words,'bit_differences':0,
            'actual_sha256':digest(folder/'outputs/actual.f32le'),
            'reference_sha256':digest(folder/'outputs/reference.f32le'),
            'recomputed_sha256':hashlib.sha256(expected.astype('<f4').tobytes()).hexdigest(),
            'log_sha256':digest(folder/'run.log')}


def verify(out: Path) -> dict:
    f = out/'silu_tests.log'
    if not f.is_file(): f = out/'compile_emit_silu.log'
    text = re.sub(r'\x1b\[[0-9;]*[mK]','',f.read_text())
    require('SILU_VECTOR_EXACT_PASS checked_fp32=192 lanes=16' in text,'missing parallel SiLU arithmetic')
    require('All tests passed' in text and not re.search(r'\*\*\* FAILED|\*\*\* ABORTED|\[error\]',text),'incomplete Chisel tests')
    outputs = {'MatrixPipeline':np.concatenate([pipeline_values(255,5,64),pipeline_values(85,5,17),pipeline_values(1,1,16)]),
               'MatrixErrors':np.tile(pipeline_values(255,5,4),5),
               'StreamingDense':np.concatenate([dense_values(*x) for x in DENSE_CASES])}
    reports = {kind:check_outputs(out/kind,expected) for kind,expected in outputs.items()}
    lines = (out/'MatrixPipeline/run.log').read_text().splitlines()
    require(lines.count('PIPELINE_CASE_PASS mask=255 contexts=5 depth=64 requests=320 issue_span=320 checked=1310720')==1,'production Matrix failed II=1')
    require(lines.count('MATRIX_PIPELINE_NUMERIC_PASS checked_fp32=1724416 bit_differences=0 physical_slices=8 wide_steps=421 original_arithmetic=1 ii_one_5contexts=1')==1,'incomplete Matrix coverage')
    errors = (out/'MatrixErrors/run.log').read_text()
    require(re.findall(r'^PIPELINE_ERROR_RECOVERY_PASS mode=(\d+) ',errors,re.M)==['0','1','2','3','4'],'missing Matrix recovery')
    require(errors.splitlines().count('PIPELINE_FAILURE_GATE_PASS cases=5 reset_recoveries=5 recovered_fp32=409600 bit_differences=0')==1,'Matrix recovery coverage')
    dense = (out/'StreamingDense/run.log').read_text()
    want = [(16,1536,64,0),(17,528,128,0),(1,16,16,0),(16,1280,32,0),
            (16,1536,64,1),(16,1536,64,0),(16,528,32,2),(16,528,32,0)]
    got = [tuple(map(int,x)) for x in re.findall(r'^STREAM_DENSE_CASE_PASS m=(\d+) n=(\d+) k=(\d+) fault=(\d+) ',dense,re.M)]
    require(got==want,'Dense execution shape/fault mismatch')
    require(dense.splitlines().count(f'STREAM_DENSE_NUMERIC_PASS cases=8 numeric_cases=6 fault_resets=2 checked_fp32={outputs["StreamingDense"].size} bit_differences=0 real_idma=1 physical_mac=4096 same_dut=1')==1,'incomplete Dense coverage')
    topology = {}
    for kind,dma in [('MatrixPipeline',0),('StreamingDense',1)]:
        sv = out/kind/'generated'/f'{kind}Probe.sv';found = counts(sv.read_text(),kind+'Probe')
        require(found['qwen2_matrix_command_endpoint']==8 and found['MatrixPipelineService']==1,'not production eight-slice Matrix')
        require(found['idma_backend_rw_axi_flat_wrap']==dma,'unexpected DMA topology')
        topology[kind] = {'physical_512mac_slices':8,'logical_matrix_engines':1,'idma_instances':dma,'generated_sha256':digest(sv)}
    return {'status':'PASS_PRODUCTION_PIPELINE_COMPONENT_ARITHMETIC_AND_RECOVERY',
            'outputs':reports,'topology':topology,'silu_lanes':16,'silu_checked_fp32':192,
            'matrix_full_width_issue_span':320,'matrix_full_width_accepted_steps':320,
            'matrix_reset_recoveries':5,'dense_reset_recoveries':2,
            'checker_runs_rtl':False,'actual_simulation_required':True,
            'full_block_acceptance':False,'dc_signoff':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    try:
        if a.output: require(not a.output.exists() and not a.output.is_symlink(),'preserve existing evidence')
        result=verify(a.evidence.resolve());text=json.dumps(result,indent=2,allow_nan=False)+'\n'
        if a.output:
            with a.output.open('x') as f:f.write(text)
        print(text,end='')
    except (ValueError,OSError,KeyError,TypeError,OverflowError) as e:
        raise SystemExit('PIPELINE_COMPONENT_REJECTED: '+str(e))
