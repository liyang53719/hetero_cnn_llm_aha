"""New original AVX512 reference-only identity; unchanged original full32768 -> BF16 -> 1024 RoPE path."""
import argparse
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
from fixture_gate import Gate, frozen, sha, need, write_failure


def execute(args):
    out = args.output
    out.mkdir(exist_ok=False)
    gate = Gate(out, ['rope1024'])
    f = frozen()
    need(os.environ.get('ATEN_CPU_CAPABILITY') == 'avx512', 'CPU_PROOF')
    for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        need(os.environ.get(name) == '4', 'CPU_PROOF')
    import torch
    import transformers
    from transformers.models.qwen2 import modeling_qwen2 as m
    from transformers.models.qwen2.configuration_qwen2 import Qwen2Config
    def raw(t): return t.detach().contiguous().view(torch.uint8).numpy().tobytes()
    need(torch.__version__ == '2.10.0+cpu' and transformers.__version__ == '4.40.1' and torch.version.git_version == '449b1768410104d3ed79d3bcfe4ba1d65c7f22c0', 'PRECHECK_PIN')
    sidecar = f['runtime_sidecar']['content']
    for name, expected in sidecar['module_sha256'].items():
        need(sha(inspect.getfile(importlib.import_module(name))) == expected, 'PRECHECK_PIN')
    for rel, expected in sidecar['native_file_sha256'].items():
        need(sha(args.site / rel) == expected, 'PRECHECK_PIN')
    p = args.config
    need(sha(p) == 'a58e896d2756a7947f23f3db55667c19ca3b8524188a30c8c640cd7ff72a5136', 'PRECHECK_PIN')
    cfg = Qwen2Config(**json.loads(p.read_text()))
    torch.set_num_threads(4); torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True); torch.set_float32_matmul_precision('highest')
    need(torch.get_default_dtype() == torch.float32 and torch.backends.cpu.get_cpu_capability() == 'AVX512', 'CPU_PROOF')
    need(torch.get_num_threads() == 4 and torch.get_num_interop_threads() == 1, 'CPU_PROOF')
    # Exact official decoder's rotary constructor: full32768 FP32 cache, then module BF16 conversion.
    rot = m.Qwen2RotaryEmbedding(cfg.hidden_size // cfg.num_attention_heads, max_position_embeddings=cfg.max_position_embeddings, base=cfg.rope_theta).to(dtype=torch.bfloat16, device='cpu')
    with torch.inference_mode(), torch.autocast('cpu', enabled=False):
        cos, sin = rot(torch.empty(0, dtype=torch.bfloat16), seq_len=1024)
    need(tuple(cos.shape) == tuple(sin.shape) == (1024, 128), 'REFERENCE_GEOMETRY', 'rope1024')
    need(torch.equal(cos[:, :64], cos[:, 64:]) and torch.equal(sin[:, :64], sin[:, 64:]), 'ROPE_HASH', 'rope1024')
    old = args.reference / 'input_only'
    # Independently recheck the frozen prefix pins before direct new-byte equality.
    for name, tensor in (('rope_cos', cos[:128].float()), ('rope_sin', sin[:128].float())):
        expected = f['frozen_fixture']['tensor_records'][name]
        source = old / (name + '.bin')
        need(source.stat().st_size == expected['bytes'] and sha(source) == expected['sha256'], 'PRECHECK_PIN')
        need(raw(tensor) == source.read_bytes(), 'ROPE_HASH', 'rope1024')
    table = torch.stack((cos[:, :64], sin[:, :64])).float()
    data = raw(table)
    digest = gate.check('rope1024', list(table.shape), 'FP32', data)
    gate.finish()
    (out / 'rope_fp32.bin').write_bytes(data)
    for rel, expected in sidecar['native_file_sha256'].items():
        need(sha(args.site / rel) == expected, 'PRECHECK_PIN')
    (out / 'RESULT.json').write_text(json.dumps(dict(status='PASS_EXACT_VISIBLE_ROPE', sha256=digest, bytes=len(data), observed_capability=torch.backends.cpu.get_cpu_capability(), threads=torch.get_num_threads(), interop=torch.get_num_interop_threads(), affinity=sorted(os.sched_getaffinity(0)), actual128_prefix_byte_equal=True)) + '\n')


def main():
    ap = argparse.ArgumentParser()
    for name in ('config', 'reference', 'output', 'site'):
        ap.add_argument('--' + name, type=Path, required=True)
    args = ap.parse_args()
    try:
        execute(args)
    except BaseException as exc:
        write_failure(args.output, exc)
        raise

if __name__ == '__main__':
    main()
