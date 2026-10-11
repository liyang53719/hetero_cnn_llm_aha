#!/usr/bin/env python3
"""Bounded Qwen2 L0 RMS1536 / RoPE table audit; never a policy acceptance.

Reads sealed cold/carried captures. Executes only RMS and table generation,
never attention, projections, a block/model forward, RTL, or a weight download.
All outputs and backend source evidence must stay in ignored work/.
"""
from __future__ import annotations

import argparse
import ctypes
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STATUS = 'DIAGNOSTIC_NOT_ACCEPTED'
TORCH_COMMIT = '449b1768410104d3ed79d3bcfe4ba1d65c7f22c0'
RUNS = {
    'cold_m16': ('qwen2_bf16_candidate_v1_m16_final_20261011',
                 'c1130e1d979cc052769d7bfc35d170461e9d84bf8e594d326401bc3a63448a41'),
    'cold_m128': ('qwen2_bf16_candidate_v1_m128_final_20261011',
                  '7b7de4815daf592b9a807f9057788b7aa815381f2e9c2e65e73ecf18b2c4bb29'),
    'carried_m16': ('qwen2_carried_candidate_m16_final_20261011',
                    '24b2c1b48549540cc8689701a270c6e80c1d79b9151a8c40676b7f2a1e773a52'),
    'carried_m128': ('qwen2_carried_candidate_m128_final_20261011',
                     '316b962a61bc53adc5b8d2a0885c977e1fffb52af05ed3667a6494f003eb59c6'),
}
NODES = ('x', 'n0', 'r', 'n1', 'cos', 'sin')
SCALARS = ('sum', 'mean', 'variance', 'root', 'inverse')
VECTORS = ('squares', 'normalized', 'normalized_bf16', 'weighted', 'output')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bf16(x):
    x = np.asarray(x, dtype='<f4')
    require(np.isfinite(x).all(), 'nonfinite BF16 input')
    u = x.view('<u4')
    y = ((u + 0x7fff + ((u >> 16) & 1)) & 0xffff0000).view('<f4')
    require(np.isfinite(y).all(), 'BF16 overflow')
    return y


def compare(a, b):
    a, b = np.asarray(a, dtype='<f4'), np.asarray(b, dtype='<f4')
    require(a.shape == b.shape and a.size > 0, 'comparison shape')
    require(np.isfinite(a).all() and np.isfinite(b).all(), 'nonfinite comparison')
    mismatch = a.view('<u4') != b.view('<u4')
    delta = np.abs(a.astype(np.float64) - b.astype(np.float64))
    return dict(shape=list(a.shape), elements=int(a.size),
                different_elements=int(mismatch.sum()), bit_exact=not bool(mismatch.any()),
                max_abs=float(delta.max()), mean_abs=float(delta.mean()),
                first_difference=(np.argwhere(mismatch)[0].tolist() if mismatch.any() else None),
                actual_sha256=sha(a.tobytes()), reference_sha256=sha(b.tobytes()))


def square_sum1536(squares):
    """Torch210 CPU SumKernel: V8, ILP4, level_step16, three blocks.

    Sum's AVX512 dispatch is explicitly disabled. multi_row_sum combines each
    residue's three 16-term blocks, folds residues 0..3, then scalar lanes 0..7.
    This is deliberately width-specific, and not the existing GDN1024 policy.
    """
    require(squares.shape[-1] == 1536, 'Qwen2 diagnostic requires width 1536')
    lane_sums = np.zeros(squares.shape[:-1] + (8,), dtype='<f4')
    for residue in range(4):
        residue_sum = np.zeros_like(lane_sums)
        for block in range(3):
            partial = np.zeros_like(lane_sums)
            for term in range(16):
                first = block * 512 + term * 32 + residue * 8
                partial = np.add(partial, squares[..., first:first + 8], dtype=np.float32)
            residue_sum = np.add(residue_sum, partial, dtype=np.float32)
        lane_sums = np.add(lane_sums, residue_sum, dtype=np.float32)
    total = np.zeros(squares.shape[:-1] + (1,), dtype='<f4')
    for lane in range(8):
        total = np.add(total, lane_sums[..., lane:lane + 1], dtype=np.float32)
    return total


def rms_recipe(x, gamma, legacy=False):
    """Explicit FP32 nodes; BF16 before direct gamma, then BF16 output.

    Candidate mean DIVIDES by1536, matching CPU sum_out().div_(). Legacy
    sequential sum / multiplication by rounded reciprocal is kept as a control.
    sqrt then division are two separate RNE nodes, not a single correctly
    rounded mathematical reciprocal-square-root operation.
    """
    x, gamma = np.asarray(x, dtype='<f4'), np.asarray(gamma, dtype='<f4')
    require(x.ndim == 3 and x.shape[0] == 1 and x.shape[-1] == 1536
            and 1 <= x.shape[1] <= 128 and gamma.shape == (1536,), 'RMS geometry')
    require(np.isfinite(x).all() and np.isfinite(gamma).all(), 'nonfinite RMS input')
    require(not np.any(x.view('<u4') & 0xffff) and not np.any(gamma.view('<u4') & 0xffff),
            'fixed BF16 input and direct gamma required')
    squares = np.multiply(x, x, dtype=np.float32)
    if legacy:
        total = np.zeros(x.shape[:-1] + (1,), dtype='<f4')
        for lane in range(1536):
            total = np.add(total, squares[..., lane:lane + 1], dtype=np.float32)
        mean = np.multiply(total, np.float32(1 / 1536), dtype=np.float32)
    else:
        total = square_sum1536(squares)
        mean = np.divide(total, np.float32(1536), dtype=np.float32)
    variance = np.add(mean, np.float32(1e-6), dtype=np.float32)
    root = np.sqrt(variance, dtype=np.float32)
    inverse = np.divide(np.float32(1), root, dtype=np.float32)
    normalized = np.multiply(x, inverse, dtype=np.float32)
    normalized_bf16 = bf16(normalized)
    weighted = np.multiply(normalized_bf16, gamma, dtype=np.float32)
    output = bf16(weighted)
    stages = dict(zip(SCALARS, (total, mean, variance, root, inverse)))
    stages.update(zip(VECTORS, (squares, normalized, normalized_bf16, weighted, output)))
    require(all(np.isfinite(v).all() for v in stages.values()), 'nonfinite RMS node')
    return stages


def rational(x):
    return Fraction.from_float(float(np.float32(x)))


def check_scalar_rne(variance, root, total, mean, inverse):
    """Exact rational midpoint checks, independent of host sqrt/div rounding."""
    def bounds(value):
        require(float(value) > 0 and np.isfinite(value), 'positive RNE result required')
        lo = np.nextafter(value, np.float32(-np.inf), dtype=np.float32)
        hi = np.nextafter(value, np.float32(np.inf), dtype=np.float32)
        return (rational(lo) + rational(value)) / 2, (rational(value) + rational(hi)) / 2

    def inside(exact, value, square=False):
        low, high = bounds(value)
        if square:
            low, high = low * low, high * high
        even = not (np.float32(value).view('<u4').item() & 1)
        return (low < exact < high) or (even and exact in (low, high))

    for v, r, t, m, inv in zip(variance.flat, root.flat, total.flat, mean.flat, inverse.flat):
        require(inside(rational(v), r, square=True), 'sqrt is not FP32 RNE')
        require(inside(Fraction(1) / rational(r), inv), 'reciprocal is not FP32 RNE')
        if t == 0:
            require(m == 0, 'zero mean')
        else:
            require(inside(rational(t) / 1536, m), 'mean division is not FP32 RNE')
    return dict(rows=int(variance.size), sqrt_rne=True, reciprocal_rne=True, mean_division_rne=True,
                method='exact integer-rational midpoint inequalities, ties-even')


C_SOURCE = r'''
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <fenv.h>
#include <float.h>
static float bf(float x) { uint32_t u; memcpy(&u,&x,4); u=(u+0x7fff+((u>>16)&1))&0xffff0000; memcpy(&x,&u,4); return x; }
int environment(void) { return sizeof(float)==4 && FLT_RADIX==2 && FLT_MANT_DIG==24 && fegetround()==FE_TONEAREST; }
int rms(const float *x, const float *g, unsigned rows, float *o) {
  if (!environment() || rows<1 || rows>128) return 0;
  for(unsigned r=0;r<rows;r++) {
    float s[1536]; for(unsigned j=0;j<1536;j++) s[j]=x[r*1536+j]*x[r*1536+j];
    float total=0;
    for(unsigned lane=0;lane<8;lane++) {
      float lanesum=0;
      for(unsigned res=0;res<4;res++) {
        float residue=0;
        for(unsigned block=0;block<3;block++) {
          float partial=0;
          for(unsigned term=0;term<16;term++) partial=partial+s[block*512+term*32+res*8+lane];
          residue=residue+partial;
        }
        lanesum=lanesum+residue;
      }
      total=total+lanesum;
    }
    float mean=total/1536.0f,variance=mean+1e-6f,root=sqrtf(variance),inverse=1.0f/root;
    const float scalars[5]={total,mean,variance,root,inverse};
    for(unsigned k=0;k<5;k++) o[k*rows+r]=scalars[k];
    for(unsigned j=0;j<1536;j++) {
      float norm=x[r*1536+j]*inverse,rounded=bf(norm),weighted=rounded*g[j];
      const float values[5]={s[j],norm,rounded,weighted,bf(weighted)};
      for(unsigned k=0;k<5;k++) o[5*rows+k*rows*1536+r*1536+j]=values[k];
    }
  }
  return 1;
}
int rope(float *o) {
  if(!environment()) return 0;
  for(unsigned j=0;j<64;j++) {
    float exponent=(float)(2*j)/128.0f,power=powf(1000000.0f,exponent),inverse=1.0f/power;
    o[j]=exponent;o[64+j]=power;o[128+j]=inverse;
    for(unsigned t=0;t<256;t++) {
      unsigned i=t*64+j;float angle=(float)t*inverse,c=cosf(angle),s=sinf(angle);
      o[192+i]=angle;o[192+16384+i]=c;o[192+2*16384+i]=s;
      o[192+3*16384+i]=bf(c);o[192+4*16384+i]=bf(s);
    }
  }
  return 1;
}
'''


def build_c(output):
    source = output / 'independent.c'
    source.write_text(C_SOURCE)
    binary = output / 'independent.so'
    command = ['/usr/bin/gcc', '-O2', '-std=c11', '-shared', '-fPIC', '-fno-fast-math',
               '-ffp-contract=off', '-fno-tree-vectorize', '-fno-builtin', str(source), '-lm', '-o', str(binary)]
    done = subprocess.run(command, text=True, capture_output=True, timeout=30)
    (output / 'build.log').write_text(done.stdout + done.stderr)
    require(done.returncode == 0, 'independent ordinary C compile failed')
    lib = ctypes.CDLL(str(binary))
    ptr = np.ctypeslib.ndpointer(dtype=np.dtype('<f4'), flags='C_CONTIGUOUS')
    lib.rms.argtypes = [ptr, ptr, ctypes.c_uint, ptr]
    lib.rope.argtypes = [ptr]
    require(lib.environment() == 1, 'C FP32 rounding environment')
    return lib, dict(command=command, source_sha256=sha(source.read_bytes()),
                     binary_sha256=sha(binary.read_bytes()),
                     compiler=subprocess.check_output(['/usr/bin/gcc', '--version'], text=True).splitlines()[0])


def c_rms(lib, x, gamma):
    rows = x.shape[1]
    data = np.empty(5 * rows + 5 * rows * 1536, dtype='<f4')
    require(lib.rms(np.ascontiguousarray(x), np.ascontiguousarray(gamma), rows, data) == 1, 'C RMS failed')
    stages = {name: data[i * rows:(i + 1) * rows].reshape(1, rows, 1) for i, name in enumerate(SCALARS)}
    offset, words = 5 * rows, rows * 1536
    stages.update({name: data[offset + i * words:offset + (i + 1) * words].reshape(x.shape)
                   for i, name in enumerate(VECTORS)})
    return stages


class Evidence:
    def __init__(self, root):
        self.root, self.files = root.resolve(), {}

    def read(self, path, digest=None):
        path = Path(path).absolute()
        require(not path.is_symlink() and path.resolve().is_relative_to(self.root), 'evidence path escape or symlink')
        raw = path.read_bytes()
        actual = sha(raw)
        require(digest is None or digest == actual, 'sealed evidence digest mismatch: ' + str(path))
        self.files[str(path.relative_to(self.root))] = dict(bytes=len(raw), sha256=actual)
        return raw

    def tensor(self, path, shape, digest):
        raw = self.read(path, digest)
        require(len(raw) == math.prod(shape) * 4, 'sealed tensor byte length')
        value = np.frombuffer(raw, dtype='<f4').reshape(shape).copy()
        require(np.isfinite(value).all(), 'nonfinite sealed tensor')
        return value

    def verify(self):
        for name, record in self.files.items():
            raw = (self.root / name).read_bytes()
            require(len(raw) == record['bytes'] and sha(raw) == record['sha256'], 'consumed source changed: ' + name)


def load_captures(evidence):
    captures = {}
    for label, (name, digest) in RUNS.items():
        path = ROOT / 'work' / name
        report = json.loads(evidence.read(path / 'RESULT.json', digest))
        require(report['status'] == STATUS and report['tokens'] == (16 if label.endswith('m16') else 128),
                'capture scope/status drift')
        byname = {r['name']: r for r in report['tensors']}
        groups = {'actual': {n: evidence.tensor(path / 'tensors' / byname[n]['path'],
                    byname[n]['shape'], byname[n]['sha256']) for n in NODES}}
        if label.startswith('cold'):
            native_dir = Path(report['native_directory'])
            native = json.loads(evidence.read(native_dir / 'RESULT.json', report['native_result_sha256']))
            records = native['modes']['bf16']['phases'][0]['stages']
            groups['official'] = {n: evidence.tensor(native_dir / records[n]['native_file'],
                        records[n]['shape'], records[n]['native_file_sha256']) for n in NODES}
            identity = native['identity']
        else:
            frozen = json.loads(evidence.read(path / 'FROZEN.json', report['frozen_sha256']))
            require(frozen['official_reference_identity'] == report['official_reference_identity'], 'runtime receipt drift')
            inventory = {r['path']: r for r in report['artifacts']}
            for method in ('official_self_cache', 'official_candidate_cache'):
                groups[method] = {}
                for n in NODES:
                    file = 'references/' + method + '/' + n + '.f32le'
                    groups[method][n] = evidence.tensor(path / file, byname[n]['shape'], inventory[file]['sha256'])
            identity = report['official_reference_identity']
        captures[label] = dict(groups=groups, identity=identity, report=report)
    return captures


def torch_rms(module, x, gamma):
    import torch
    layer = module.Qwen2RMSNorm(1536, eps=1e-6).to(torch.bfloat16).eval()
    layer.weight = torch.nn.Parameter(torch.from_numpy(gamma.copy()).to(torch.bfloat16), requires_grad=False)
    with torch.inference_mode():
        hidden = torch.from_numpy(x.copy()).to(torch.bfloat16)
        full = hidden.float()
        squares = full.pow(2)
        total = squares.sum(-1, keepdim=True)
        mean = squares.mean(-1, keepdim=True)
        variance = mean + 1e-6
        inverse = torch.rsqrt(variance)
        normalized = full * inverse
        rounded = normalized.to(torch.bfloat16)
        weighted = rounded.float() * layer.weight.float()
        result = layer(hidden).float().numpy()
        values = dict(sum=total, mean=mean, variance=variance, inverse=inverse, squares=squares,
                      normalized=normalized, normalized_bf16=rounded.float(), weighted=weighted)
        return result, {name: value.numpy() for name, value in values.items()}


def audit_rms(lib, module, captures, weights, output):
    cases = {}
    for label, capture in captures.items():
        for group, tensors in capture['groups'].items():
            for stage, source, gamma_name in (('n0', 'x', 'input_layernorm.weight'),
                                              ('n1', 'r', 'post_attention_layernorm.weight')):
                key = label + '/' + group + '/' + stage
                x, gamma = tensors[source], weights[gamma_name]
                recipe = rms_recipe(x, gamma)
                legacy = rms_recipe(x, gamma, legacy=True)
                independent = c_rms(lib, x, gamma)
                official, native_stages = torch_rms(module, x, gamma)
                cpp_checks = {name: compare(recipe[name], independent[name]) for name in recipe}
                native_checks = {name: compare(recipe[name], value) for name, value in native_stages.items()}
                original_check = compare(legacy['output'], tensors[stage]) if group == 'actual' else None
                capture_control = compare(official, tensors[stage]) if group != 'actual' else None
                require(all(r['bit_exact'] for r in cpp_checks.values()), 'independent C disagreement: ' + key)
                require(original_check is None or original_check['bit_exact'], 'legacy actual control mismatch: ' + key)
                require(capture_control is None or capture_control['bit_exact'], 'sealed official control mismatch: ' + key)
                same_input = compare(recipe['output'], official)
                cases[key] = dict(rows=x.shape[1], input_sha256=sha(x.tobytes()), direct_gamma_sha256=sha(gamma.tobytes()),
                    candidate_vs_official_same_input=same_input,
                    legacy_vs_official_same_input=compare(legacy['output'], official),
                    candidate_vs_original_capture=compare(recipe['output'], tensors[stage]),
                    original_actual_control=original_check, original_official_control=capture_control,
                    candidate_cpp_stage_checks=cpp_checks, candidate_official_stage_checks=native_checks,
                    scalar_rne_check=check_scalar_rne(*(recipe[n] for n in ('variance', 'root', 'sum', 'mean', 'inverse'))),
                    multiply_reciprocal_instead_of_divide=compare(
                        recipe['sum'] * np.float32(1 / 1536), recipe['mean']))
                # Save all rows' scalars plus full outputs; no worst-lane sampling.
                directory = output / 'rms' / label / group / stage
                directory.mkdir(parents=True)
                for name in SCALARS + ('output',):
                    recipe[name].tofile(directory / (name + '.f32le'))
                official.tofile(directory / 'official_same_input.f32le')
    return cases


def audit_rope(lib, module, captures, output):
    import torch
    data = np.empty(192 + 5 * 16384, dtype='<f4')
    require(lib.rope(data) == 1, 'C RoPE failed')
    scalar = {name: data[i * 64:(i + 1) * 64] for i, name in enumerate(('exponent', 'power', 'inverse'))}
    arrays = {name: data[192 + i * 16384:192 + (i + 1) * 16384].reshape(256, 64)
              for i, name in enumerate(('angle', 'cos', 'sin', 'cos_bf16', 'sin_bf16'))}
    with torch.inference_mode():
        table = module.Qwen2RotaryEmbedding(128, max_position_embeddings=256, base=1e6)
        exponent = torch.arange(0, 128, 2).float() / 128
        power = 1e6 ** exponent
        angles = torch.outer(torch.arange(256).float(), table.inv_freq)
        official = {'cos': table.cos_cached.numpy(), 'sin': table.sin_cached.numpy()}
        native_scalar = {'exponent': exponent.numpy(), 'power': power.numpy(), 'inverse': table.inv_freq.numpy()}
    require(table.cos_cached.dtype == table.sin_cached.dtype == torch.float32, 'official initial table dtype')
    checks = {name: compare(scalar[name], native_scalar[name]) for name in scalar}
    checks['angle'] = compare(arrays['angle'], angles.numpy())
    controls, tables = {}, {}
    for trig in ('cos', 'sin'):
        candidate = np.concatenate((arrays[trig], arrays[trig]), axis=1)
        materialized = np.concatenate((arrays[trig + '_bf16'], arrays[trig + '_bf16']), axis=1)
        require(compare(bf16(candidate), materialized)['bit_exact'], 'C/Python BF16 table mismatch')
        native_bf16 = bf16(official[trig])
        original = np.array([[getattr(math, trig)(t / math.pow(1e6, 2 * j / 128))
                             for j in range(64)] for t in range(256)], dtype='<f4')
        original = bf16(np.concatenate((original, original), axis=1))
        tables[trig] = dict(fp32_candidate_vs_official=compare(candidate, official[trig]),
                            bf16_candidate_vs_official=compare(materialized, native_bf16),
                            legacy_double_libm_vs_official=compare(original, native_bf16))
        for label, capture in captures.items():
            for group, tensors in capture['groups'].items():
                size = tensors[trig].shape[0]
                reference = original[:size] if group == 'actual' else native_bf16[:size]
                result = compare(reference, tensors[trig])
                controls[label + '/' + group + '/' + trig] = result
                require(result['bit_exact'], 'sealed table control mismatch: ' + label + '/' + group + '/' + trig)
        (output / 'rope').mkdir(exist_ok=True)
        for name, values in (('candidate_fp32', candidate), ('official_fp32', official[trig]),
                             ('candidate_bf16', materialized), ('official_bf16', native_bf16)):
            values.tofile(output / 'rope' / (trig + '_' + name + '.f32le'))
    for name, values in {**scalar, 'angle': arrays['angle']}.items():
        values.tofile(output / 'rope' / (name + '.f32le'))
    return dict(positions=[0, 255], distinct_frequencies=64, split_half_width=128,
                scalar_checks=checks, tables=tables, sealed_table_controls=controls,
                recipe='FP32 exponent; glibc powf; FP32 reciprocal; FP32 position multiplication; glibc cosf/sinf; BF16 RNE',
                fp32_bit_equivalence_claimed=False, cross_host_equivalence_claimed=False,
                official_table_uses='Torch CPU MKL VML HA sin/cos on initial FP32 cache; subsequent BF16 cast')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--payload', type=Path, default=ROOT / 'work/qwen2_layer0_payload_20261011')
    parser.add_argument('--source-evidence', type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    require(not output.exists() and output.is_relative_to(ROOT / 'work'), 'fresh ignored work output required')
    evidence = Evidence(ROOT)
    sys.path.insert(0, str(ROOT / 'scripts'))
    import qwen2_layer0_model_gate as native
    import torch
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    require(torch.__version__ == '2.10.0+cpu' and torch.version.git_version == TORCH_COMMIT, 'Torch runtime drift')
    require(torch.backends.cpu.get_cpu_capability() == 'AVX512', 'observed host capability drift')
    require(os.getenv('ATEN_CPU_CAPABILITY') is None, 'unexpected dispatch override')
    module, identity = native.runtime_identity(ROOT)
    captures = load_captures(evidence)
    require(all(c['identity'] == identity for c in captures.values()), 'official capture runtime changed')
    pin = json.loads(evidence.read(ROOT / 'config/payload_pins/qwen2_layer0.json',
                                  '190e1fca0edff7c783c6981a6759f57162e63c4754ffc0f3481df64de9d06f88'))
    manifest = json.loads(evidence.read(args.payload / 'manifest.json'))
    manifest_byname = {r['local_name']: r for r in manifest['tensors']}
    weights = {}
    for record in pin['tensors']:
        name = record['local_name']
        if name in ('input_layernorm.weight', 'post_attention_layernorm.weight'):
            require(record['shape'] == [1536] and record['dtype'] == 'BF16', 'gamma pin geometry')
            require(manifest_byname[name]['sha256'] == record['sha256'], 'gamma manifest pin mismatch')
            raw = evidence.read(args.payload / (name + '.bin'), record['sha256'])
            require(len(raw) == 1536 * 2, 'gamma byte length')
            weights[name] = (np.frombuffer(raw, dtype='<u2').astype('<u4') << 16).view('<f4')
    require(len(weights) == 2, 'both fixed direct gamma weights required')
    for name in ('scripts/qwen2_layer0_model_gate.py', 'spec/numerical_contract.md',
                 'config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py',
                 'scripts/qwen2_carried_prefill_candidate.py'):
        evidence.read(ROOT / name)
    require(sha((ROOT / 'scripts/qwen2_carried_prefill_candidate.py').read_bytes()) ==
            '9df9ad51f98c7273ce8847a47a090093edd23c48289cf9e964f44a8ac3cd41b6', 'carried source drift')
    require(args.source_evidence.is_dir(), 'pinned backend source evidence required')
    source_manifest = json.loads(evidence.read(args.source_evidence / 'source_manifest.json',
                    '52555a6d4b7b307e7e87bb2cb6bfcaf4b20d27fa58046ef50ea78427a38dcbf9'))
    require(len(source_manifest) == 14, 'backend source coverage drift')
    for entry in source_manifest:
        require('/' + TORCH_COMMIT + '/' in entry['source'], 'unpinned backend URL')
        raw = evidence.read(args.source_evidence / Path(entry['file']).name, entry['sha256'])
        require(len(raw) == entry['bytes'], 'backend source length mismatch')
    evidence.read(Path(__file__))
    output.mkdir(parents=True)
    lib, build = build_c(output)
    policy = native.load_policy(ROOT)
    frozen = dict(status=STATUS, scope='QWEN2_L0_RMS1536_AND_ROPE_0_255_MODEL_ONLY',
                  generator_sha256=sha(Path(__file__).read_bytes()), inputs=evidence.files,
                  official_reference_identity=identity, backend=dict(torch_commit=TORCH_COMMIT,
                    reported_cpu_capability=torch.backends.cpu.get_cpu_capability(),
                    sum_dispatch='AVX2 V8 (AVX512 pointer disabled by REGISTER_DISPATCH)',
                    rsqrt_dispatch='AVX2; sqrt then reciprocal with separate FP32 rounding',
                    table_trig_backend='MKL VML HA; explicit FTZ/DAZ off',
                    machine=platform.machine(), libc=platform.libc_ver(), threads=4,
                    interop_threads=1, deterministic_algorithms=True),
                  independent_c=build, threshold_policy=policy, full_block_executed=False,
                  rtl_executed=False, policy_changed=False, numerical_v0_unchanged=True)
    frozen_bytes = (json.dumps(frozen, indent=2) + '\n').encode()
    (output / 'FROZEN.json').write_bytes(frozen_bytes)
    started = time.monotonic()
    rms = audit_rms(lib, module, captures, weights, output)
    rope = audit_rope(lib, module, captures, output)
    evidence.verify()
    require(sha((output / 'FROZEN.json').read_bytes()) == sha(frozen_bytes), 'diagnostic freeze changed')
    result = dict(**frozen, frozen_sha256=sha(frozen_bytes), rms_cases=rms, rope=rope,
                  all_rms_bf16_same_input_exact=all(c['candidate_vs_official_same_input']['bit_exact'] for c in rms.values()),
                  all_rms_reported_fp32_stages_exact=all(all(v['bit_exact'] for v in c['candidate_official_stage_checks'].values()) for c in rms.values()),
                  all_rope_bf16_entries_exact=all(v['bf16_candidate_vs_official']['bit_exact'] for v in rope['tables'].values()),
                  full_block_improvement_unmeasured=True, seconds=time.monotonic() - started,
                  files={str(p.relative_to(output)): dict(bytes=p.stat().st_size, sha256=sha(p.read_bytes()))
                         for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'FROZEN.json'})
    (output / 'RESULT.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'all_rms_bf16_same_input_exact',
                      'all_rms_reported_fp32_stages_exact', 'all_rope_bf16_entries_exact', 'seconds')}, indent=2))
    # This diagnostic is deliberately never an acceptance command.
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
