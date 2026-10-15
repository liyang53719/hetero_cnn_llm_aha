"""Bounded same-input gate arithmetic diagnostic; no block/CI/RTL acceptance.

Cold by default. Raw checkpoint inputs produce a fresh original-AST n1; the
original full-geometry gate Linear is compared only at fixed sampled columns
against the existing native Matrix kernel and original BF16 materialization.
No historical reference or DUT intermediate is an arithmetic input.
"""
from __future__ import annotations
import ast
import ctypes as C
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import stat
import sys
import tempfile
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'work/qwen2_ffn_gate_diagnostic/local03'
PREFIX = ROOT / 'work/qwen2_live_qkv_inputs_m128/recovered_20261015_0018/raw'
TAIL = ROOT / 'work/qwen2_live_tail_segment_recovery_m128/recovered_20261015_0027/raw'
WINDOWS = (0, 4480, 8928)
ROWS, K, WIDTH, NCOLS = 128, 1536, 8960, 32
CPU_SECONDS, AS_BYTES, OUTPUT_BYTES = 120, 4 << 30, 64 << 20
MODEL = 'config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py'
KNOWN_LIBRARY_SHA256 = 'a44f4cd7861d1207698bb3dfc89820ded30a44db1cf1c8b9f951019d1edce1fa'
SOURCE_PINS = {
 'candidates/qwen2_resident_matrix/transposed_down/model.py': '3e6f73fa8fe6ce5e78b4578335e82d7e593d0cce0b35e8f401dc045e1df59412',
 'candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp': 'bdd7513bd788c03ac92be1d7c2f3553d3d7e0723ce1ac2892e93dcef58782ef1',
 'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp': '7702e5975ff04393deb4969835eb5ffcfbb99258329ee6ac27fd75b289356e14',
 'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py': 'b3a3b61a0414ab72d67d6de192b79de332fddc64b459c55a6f7f5ff149abaa27',
 'candidates/qwen2_resident_matrix/official_bf16/dense_silu.py': 'dfd44e15f274090ba7d1eca4fa6c59248e11029dad3c5fcfc0b45693c6267699',
 'candidates/qwen2_resident_matrix/ffn_fullgroup/check_numeric.py': '7fd62ea5f59af4ba6da36d74b289e0aba85b1eb35b1d3e060a7d8e95d0b55336',
 'candidates/qwen2_resident_matrix/ffn_window/model.py': '1c9f69beed57b96f6003c199fd02a9d362c16b6fff71ba93a18fb1f10f5eaae4',
 'candidates/qwen2_resident_matrix/dense_block_reduce/matrix_binding.py': '33ea0786d537aa7de59b19ff55cb515f2afeaee780f4a9f1faeb42402da19593',
 'candidates/qwen2_resident_matrix/ffn_public/execute_numeric.py': 'fa550e3b9df4aca6041eb3631f50e520fda762184db5bcaf70e707a7dc72ffb3',
 'scripts/qwen2_layer0_model_gate.py': '917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85',
}
EXPECTED = dict(torch='2.10.0+cpu', commit='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0',
                capability='AVX2', threads=4, interop_threads=1,
                mkldnn_enabled=False, deterministic=True)


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def file_identity(path):
    """Canonical regular-file identity; reject aliases and concurrent changes."""
    path = Path(path)
    need(path.is_absolute() and str(path) == str(path.resolve(strict=True)), 'canonical absolute file path required')
    need(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink artifact refused')
    need(path.is_file(), 'regular artifact required before open')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode), 'regular artifact required')
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
        after = os.fstat(stream.fileno())
    keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    need(all(getattr(before, k) == getattr(after, k) == getattr(path.stat(), k) for k in keys),
         'artifact changed during identity read')
    return dict(path=str(path), bytes=after.st_size, sha256=digest.hexdigest())


def artifact_snapshot(receipt_path, library_path, compiler_path, dense):
    return dict(receipt=file_identity(receipt_path), library=file_identity(library_path),
                compiler=file_identity(compiler_path),
                sources={name: file_identity(ROOT/name) for name in dense.SOURCE_CLOSURE})


def prepare_native_artifact(receipt_path, expected_receipt_sha256, dense):
    """Verify explicitly supplied local provenance before the no-process audit.

    The receipt hash must arrive independently from the CLI/caller. The tracked
    verifier checks schema, policy, both SiLU ABI names, compiler, strict flags,
    source closure and ELF. Its fixed g++ --version probe has a 10-second bound.
    This loads no shared library and performs no numeric or compiler build work.
    """
    need(isinstance(expected_receipt_sha256, str) and len(expected_receipt_sha256) == 64 and
         all(c in '0123456789abcdef' for c in expected_receipt_sha256), 'independent receipt SHA256 required')
    need(isinstance(receipt_path, (str, Path)), 'explicit native receipt path required')
    identity = file_identity(receipt_path)
    need(0 < identity['bytes'] <= 262144 and identity['sha256'] == expected_receipt_sha256,
         'external native receipt identity mismatch')
    raw = Path(receipt_path).read_bytes()
    need(hashlib.sha256(raw).hexdigest() == expected_receipt_sha256, 'receipt changed before parsing')
    data = json.loads(raw)
    need(isinstance(data, dict) and isinstance(data.get('compiler'), dict), 'native receipt object required')
    need(data.get('library_sha256') == KNOWN_LIBRARY_SHA256, 'known original native ELF required')
    before = artifact_snapshot(receipt_path, data['library'], data['compiler']['path'], dense)
    need(before['receipt'] == identity and before['library']['sha256'] == KNOWN_LIBRARY_SHA256,
         'receipt or known ELF changed')
    verified = dense.verify_library(data)
    need(verified == data, 'tracked verifier changed receipt')
    need(artifact_snapshot(receipt_path, data['library'], data['compiler']['path'], dense) == before,
         'native artifact/source changed during verification')
    return before


def recheck_native_artifact(artifact, dense):
    """Byte/source checks only; safe after the no-subprocess audit is installed."""
    need(artifact_snapshot(artifact['receipt']['path'], artifact['library']['path'],
                          artifact['compiler']['path'], dense) == artifact,
         'native receipt/ELF/compiler/source changed')


def source_check():
    need(all(sha(ROOT / p) == h for p, h in SOURCE_PINS.items()), 'original gate source changed')
    # The immutable sources establish these facts, not an assumed CPU schedule.
    text = (ROOT / 'candidates/qwen2_resident_matrix/ffn_fullgroup/check_numeric.py').read_text()
    need('K, WIDTH, WINDOW = 1536, 8960, 160' in text and 'lib.td_group(0, K, 5)' in text,
         'gate original full-K group changed')
    text = (ROOT / 'candidates/qwen2_resident_matrix/dense_block_reduce/matrix_binding.py').read_text()
    need("if binding.role not in ('q_raw','k_raw','v_raw'):" in text,
         'QKV-only split dispatch changed')
    return dict(SOURCE_PINS)


def raw_specs(pins):
    # Exclude both up/down weights: there is no MLP or final-y execution.
    selected = [s for s in pins['raw_tensors']
                if s['local_name'] not in ('mlp.up_proj.weight', 'mlp.down_proj.weight')]
    need(len(selected) == 11, 'fixed raw11 inventory')
    return {s['local_name']: {**s, 'resolved': (PREFIX if s['manifest_role'] == 'prefix_raw' else TAIL)
                             / (s['local_name'] + '.bin')} for s in selected}


def gate_constructor(nodes):
    """Return the unchanged gate-only constructor assignment from original AST."""
    cls = ast.parse(nodes[27]['source']).body[0]
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    chosen = [n for n in init.body if isinstance(n, ast.Assign) and
              any(isinstance(t, ast.Attribute) and t.attr == 'gate_proj' for t in n.targets)]
    need(len(chosen) == 1, 'unique original gate constructor')
    return ast.Module(body=chosen, type_ignores=[])


def payload_audit(allowed_raw, output):
    allowed_raw = {str(p.resolve()) for p in allowed_raw}
    output = output.resolve()
    def audit(event, args):
        if event in ('subprocess.Popen', 'os.fork', 'os.forkpty', 'os.posix_spawn', 'os.exec', 'os.system'):
            raise ValueError('diagnostic cannot spawn a process')
        if event != 'open' or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        p = Path(os.fsdecode(args[0])).resolve()
        mode, flags = args[1:3]
        writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or bool(
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing:
            need(p.is_relative_to(output), 'writes restricted to new private output')
        if p.suffix in ('.bin', '.f32le') and not p.is_relative_to(output):
            need(str(p) in allowed_raw and not writing, 'historical/intermediate tensor read refused')
    return audit


def official_to_n1(pins, values, specs, torch, np):
    nodes = pins['model_ast_nodes']
    ns = {'torch': torch, 'nn': torch.nn, 'math': math}
    executed = []
    def execute(indices):
        for index in indices:
            item = nodes[index]
            need(hashlib.sha256(item['source'].encode()).hexdigest() == item['source_sha256'], 'official AST text drift')
            exec(compile(ast.parse(item['source']), MODEL, 'exec'), ns)
            executed.append(index)
    def tensor(name):
        return torch.from_numpy(np.frombuffer(values[name], '<u2').copy()).view(torch.bfloat16).reshape(specs[name]['shape'])
    def parameter(name):
        return torch.nn.Parameter(tensor(name), requires_grad=False)
    execute(range(4)); execute([15])
    norm = ns['Qwen2RMSNorm'](1536, eps=1e-6).to(torch.bfloat16).eval()
    norm.weight = parameter('input_layernorm.weight')
    attention = torch.nn.Module()
    attention.hidden_size, attention.num_heads, attention.num_key_value_heads = 1536, 12, 2
    attention.head_dim, attention.num_key_value_groups, attention.attention_dropout = 128, 6, 0.0
    ns['self'] = attention
    execute([4, 5, 6, 28])
    for letter in 'qkv':
        layer = getattr(attention, letter + '_proj')
        layer.weight = parameter('self_attn.' + letter + '_proj.weight')
        layer.bias = parameter('self_attn.' + letter + '_proj.bias')
    attention.o_proj.weight = parameter('self_attn.o_proj.weight')
    attention.rotary_emb = ns['Qwen2RotaryEmbedding'](128, max_position_embeddings=256, base=1e6).to(torch.bfloat16)
    attention.to(torch.bfloat16).eval()
    decoder = torch.nn.Module()
    ns.update(self=decoder, config=SimpleNamespace(hidden_size=1536, rms_norm_eps=1e-6))
    execute([30])
    decoder.post_attention_layernorm.weight = parameter('post_attention_layernorm.weight')
    decoder.to(torch.bfloat16).eval()
    holder = torch.nn.Module()
    holder.hidden_size, holder.intermediate_size = 1536, 8960
    ns['self'] = holder
    exec(compile(gate_constructor(nodes), MODEL, 'exec'), ns)
    holder.gate_proj.weight = parameter('mlp.gate_proj.weight')
    holder.to(torch.bfloat16).eval()
    for module in (norm, attention, decoder, holder):
        need(not module.training and all(p.dtype == torch.bfloat16 and not p.requires_grad
                                        for p in module.parameters()), 'all learned inputs bound')
    mask_raw = b''.join((0xff7f if k > q else 0).to_bytes(2, 'little') for q in range(128) for k in range(128))
    need(hashlib.sha256(mask_raw).hexdigest() == pins['mask_contract']['native_sha256'], 'cold causal mask identity')
    mask = torch.from_numpy(np.frombuffer(mask_raw, '<u2').copy()).view(torch.bfloat16).reshape(1, 1, 128, 128)
    with torch.inference_mode():
        x = tensor('embed_tokens.rows_0_255')[:128].unsqueeze(0).contiguous()
        ns.update(hidden_states=x, self=attention)
        execute([31])
        ns['hidden_states'] = norm(x)
        execute([7, 8, 9])
        ns.update(bsz=1, q_len=128, kv_seq_len=128, position_ids=torch.arange(128, dtype=torch.long).unsqueeze(0))
        execute(range(10, 15))
        ns['attention_mask'] = mask
        execute(range(16, 27))
        execute([32])
        ns.update(hidden_states=ns['attn_output'], self=decoder)
        execute([33, 34, 35])
        n1 = ns['hidden_states']
        need(n1.shape == (1, 128, 1536) and n1.is_contiguous(), 'original gate input geometry')
        n1_bytes = n1.view(torch.uint8).numpy().tobytes()
        official = holder.gate_proj(n1)
        need(n1.view(torch.uint8).numpy().tobytes() == n1_bytes, 'official gate mutated n1')
        need(official.shape == (1, 128, 8960), 'original gate output geometry')
    need(36 not in executed and 37 not in executed and 29 not in executed, 'MLP or final residual executed')
    return n1, official, executed


def native_gate(n1_words, weight_words, library, model, dense, np):
    """Exact original native arithmetic, with one independent physical context.

    No owner lifecycle is invented: standalone native entrypoints only. Every
    selected cell uses original owner packet mapping, k=0..1535, one FP32 FMA
    accumulator, and original final BF16 RNE. No split or pair reorder.
    """
    need(n1_words.shape == (128, 1536) and weight_words.shape == (8960, 1536), 'raw logical shapes')
    need(library.td_reset() == 0, 'native rounding reset')
    results, raw_results = [], []
    packet_hash = hashlib.sha256()
    holder = SimpleNamespace(chunk_end=1536, contexts=1)
    for ng in WINDOWS:
        need(library.td_group(0, 1536, 1) == 0, 'fresh full-K group')
        aa, bb, output = (C.c_uint16 * 16)(), (C.c_uint16 * 256)(), (C.c_uint32 * 4096)()
        for k in range(1536):
            awords = tuple(model.pack16([int(x) for x in n1_words[g:g+16, k]]) for g in range(0, 128, 16))
            bwords = tuple(model.pack16([int(x) for x in weight_words[ng+h:ng+h+16, k]]) for h in (0, 16))
            step = model.DenseOwnerModel._operand_response(holder, (k, 0, awords, bwords))
            need(step.k == k and step.clear == (k == 0) and step.last == (k == 1535), 'original packet order')
            aa[:], bb[:] = step.a, step.b
            packet_hash.update(bytes(aa)); packet_hash.update(bytes(bb))
            rc = library.td_step(step.k, step.context, step.clear, step.last, step.finish, step.emit, aa, bb, output)
            need(rc == int(step.last), 'original native arithmetic rejected')
        raw = np.empty((128, 32), dtype='<u4')
        rounded = np.empty((128, 32), dtype='<u4')
        for m in range(128):
            for n in range(32):
                r, c = model.output_coordinate(m, n)
                word = int(output[r * 256 + c])
                raw[m, n], rounded[m, n] = word, dense.bf16_rne_word(word)
        raw_results.append(raw.view('<f4')); results.append(rounded.view('<f4'))
    need(library.matrix_dense_fmas() == len(WINDOWS) * 1536 * 4096 and library.matrix_normal_fmas() == 0,
         'observed physical FMA count')
    return np.concatenate(results, axis=1), np.concatenate(raw_results, axis=1), packet_hash.hexdigest()


def run(*, execute=False, native_receipt=None, native_receipt_sha256=None):
    if not execute:
        return {'status': 'NOT_EXECUTED'}
    need(native_receipt is not None and native_receipt_sha256 is not None,
         'execute requires explicit --native-receipt and independent --native-receipt-sha256')
    started, cpu_started = time.monotonic(), time.process_time()
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (AS_BYTES, AS_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (OUTPUT_BYTES - 1, OUTPUT_BYTES - 1))
    need(not OUT.exists() and not any(n in sys.modules for n in ('torch', 'numpy')), 'fresh fixed output/process required')
    need(os.environ.get('ATEN_CPU_CAPABILITY') == 'avx2', 'ATen AVX2 required before import')
    need(os.environ.get('PYTHONPATH') == str(ROOT / 'work/runtime_recovery/site-packages'), 'fixed runtime path')
    need(all(os.environ.get(k) == v for k, v in {'OMP_NUM_THREADS': '4', 'MKL_NUM_THREADS': '4',
        'OPENBLAS_NUM_THREADS': '1', 'PYTHONNOUSERSITE': '1'}.items()), 'fixed thread/import environment')
    sys.path.insert(0, str(ROOT))
    from candidates.qwen2_runtime_relocation import runtime
    pins = runtime._expected('full29')
    native = runtime.check_native(pins, family='full29')
    sources = source_check()
    sources.update({str(p.relative_to(ROOT)): sha(p) for p in HERE.iterdir() if p.suffix == '.py'})
    need(sha(ROOT / MODEL) == pins['sources'][MODEL]['sha256'], 'original model source')
    specs = raw_specs(pins)
    from candidates.qwen2_resident_matrix.official_bf16 import dense_silu as dense
    from candidates.qwen2_resident_matrix.transposed_down import model
    artifact = prepare_native_artifact(native_receipt, native_receipt_sha256, dense)
    OUT.mkdir(parents=True)
    (OUT/'tmp').mkdir()
    tempfile.tempdir = str(OUT/'tmp')
    os.environ['TORCHINDUCTOR_CACHE_DIR'] = str(OUT/'tmp/torchinductor')
    sys.addaudithook(payload_audit([s['resolved'] for s in specs.values()], OUT))
    raw = {name: s['resolved'].read_bytes() for name, s in specs.items()}
    need(all(len(raw[n]) == s['bytes'] and hashlib.sha256(raw[n]).hexdigest() == s['sha256'] for n, s in specs.items()), 'raw11 identity')
    import numpy as np
    import torch
    torch.set_num_threads(4); torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True); torch.backends.mkldnn.enabled = False
    def state():
        return dict(torch=str(torch.__version__), commit=torch.version.git_version,
            capability=torch.backends.cpu.get_cpu_capability(), threads=torch.get_num_threads(),
            interop_threads=torch.get_num_interop_threads(), mkldnn_enabled=torch.backends.mkldnn.enabled,
            deterministic=torch.are_deterministic_algorithms_enabled())
    need(state() == EXPECTED and np.__version__ == pins['runtime_requirements']['numpy'], 'numeric runtime identity')
    build = torch.__config__.show()
    need(hashlib.sha256(build.encode()).hexdigest() ==
         '4096ae2ff210db4a4da17fe7e5ef17c7715c4e4dc5d4175a9357b83bf820075a', 'fixed AVX2 build metadata')
    need(build.count('CPU capability usage: AVX2') == 1 and
         hashlib.sha256(build.replace('CPU capability usage: AVX2', 'CPU capability usage: AVX512').encode()).hexdigest()
         == pins['runtime_requirements']['torch_build_sha256'], 'original build differs only in explicit dispatch line')
    need(str(Path(torch._C.__file__).resolve()) == native['torch_C']['path'] and
         str(Path(np._core._multiarray_umath.__file__).resolve()) == native['numpy_multiarray']['path'], 'loaded native origins')
    recheck_native_artifact(artifact, dense)
    library = dense.configure_library(C.CDLL(artifact['library']['path']))
    n1, official, executed = official_to_n1(pins, raw, specs, torch, np)
    n1_words = n1.view(torch.uint16).numpy().reshape(128, 1536).copy()
    n1_before = hashlib.sha256(n1_words.tobytes()).hexdigest()
    weights = np.frombuffer(raw['mlp.gate_proj.weight'], '<u2').reshape(8960, 1536)
    actual, raw_actual, packet_sha = native_gate(n1_words, weights, library, model, dense, np)
    need(hashlib.sha256(n1_words.tobytes()).hexdigest() == n1_before, 'native input mutated')
    columns = [n for ng in WINDOWS for n in range(ng, ng+32)]
    ref = official.float().numpy().reshape(128, 8960)[:, columns].copy()
    from scripts import qwen2_layer0_model_gate as gates
    policy = gates.load_policy(ROOT)
    need(policy['operator'] == {'max_abs': 0.03125, 'mean_abs': 0.005}, 'original numerical policy')
    metrics = gates.compare(actual, ref)
    delta = actual.astype(np.float64) - ref.astype(np.float64)
    flat = np.flatnonzero(delta.reshape(-1))
    details = [dict(row=int(i//96), column=columns[int(i%96)], actual=float(actual.reshape(-1)[i]),
                    official=float(ref.reshape(-1)[i]), error=float(delta.reshape(-1)[i]),
                    native_accumulator=float(raw_actual.reshape(-1)[i])) for i in flat]
    report = dict(schema=1, status='COMPLETED_SAMPLED_SAME_INPUT_GATE_DIAGNOSTIC',
        runtime=state(), torch_build_sha256=hashlib.sha256(build.encode()).hexdigest(), six_native_files=native, native_artifact=artifact, source_sha256=sources,
        raw11={n: dict(path=str(s['resolved']), bytes=s['bytes'], sha256=s['sha256']) for n,s in specs.items()},
        official_ast_nodes_executed=executed, official_gate_constructor='unchanged original Qwen2MLP.__init__.gate_proj assignment',
        official_input_shape=[1,128,1536], official_gate_shape=[1,128,8960],
        gate_algorithm='k0..1535 FP32 fmaf(weight,activation,accumulator); BF16 RNE once at terminal',
        qkv_k1024_512_profile_applied_to_gate=False, native_group_contexts=1, production_group_contexts=5,
        independent_per_cell_arithmetic_only=True, original_operand_mapping_executed=True,
        full_gate_native_executed=False, same_input_isolation=True,
        input_origin='fresh raw11 original-AST official n1', dut_n1_available=False,
        upstream_n1_error_propagation_measured=False, ci_private_intermediates_reused=False,
        ci_runtime_equivalence_claimed=False, historical_tensor_payload_read=False, old_pass_inherited=False,
        full_mlp_executed=False, fullblock_executed=False, owner_protocol_executed=False, rtl_executed=False,
        columns=columns, rows=list(range(128)), metrics=metrics, policy=policy,
        sampled_verdict=gates.stage_verdict('gate', metrics, 'bf16', policy), full_stage_verdict=None,
        physical_fma_calls=int(library.matrix_dense_fmas()), selected_logical_macs=128*96*1536,
        packet_sha256=packet_sha, native_n1_sha256=n1_before, differences=details,
        limits=dict(cpu_seconds=CPU_SECONDS,address_space_bytes=AS_BYTES,output_bytes_less_than=OUTPUT_BYTES),
        limitation='Only same-official-n1 sampled gate arithmetic isolated. CI DUT n1 absent; cannot measure propagation or accept full gate/block.')
    n1.float().numpy().reshape(128,1536).astype('<f4').tofile(OUT/'official_n1.f32le')
    actual.astype('<f4').tofile(OUT/'native_gate_selected.f32le')
    ref.astype('<f4').tofile(OUT/'official_gate_selected.f32le')
    raw_actual.astype('<f4').tofile(OUT/'native_accumulator_selected.f32le')
    report['outputs'] = {p.name: dict(bytes=p.stat().st_size, sha256=sha(p)) for p in OUT.rglob('*') if p.is_file()}
    need(runtime.check_native(pins,family='full29') == native and state() == EXPECTED, 'runtime changed')
    recheck_native_artifact(artifact, dense)
    need(all(sha(ROOT/p) == h for p,h in sources.items()), 'source changed')
    need(all(sha(s['resolved']) == s['sha256'] for s in specs.values()), 'raw changed')
    report.update(cpu_seconds=time.process_time()-cpu_started,wall_seconds=time.monotonic()-started,
                  max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    encoded = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+'\n').encode()
    need(sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())+len(encoded) < OUTPUT_BYTES, 'private output budget')
    (OUT/'RESULT.json').write_bytes(encoded)
    # Only fixed aggregate max/mean/count fields leave the private output.
    safe = {k: metrics[k] for k in ('max_abs','mean_abs','elements','different_elements')}
    print(json.dumps(safe, sort_keys=True))
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--native-receipt', help='Canonical absolute path to an externally supplied local compile receipt')
    parser.add_argument('--native-receipt-sha256', help='Independently established SHA256 of the exact receipt bytes')
    args = parser.parse_args()
    if args.execute and not (args.native_receipt and args.native_receipt_sha256):
        parser.error('--execute requires --native-receipt and independent --native-receipt-sha256')
    result = run(execute=args.execute, native_receipt=args.native_receipt,
                 native_receipt_sha256=args.native_receipt_sha256)
    if not args.execute:
        print(json.dumps(result))
