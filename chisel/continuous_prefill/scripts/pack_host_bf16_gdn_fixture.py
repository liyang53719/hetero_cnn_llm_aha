#!/usr/bin/env python3
"""Bounded real embedding tokens 0/1 → official inputNorm → Host Dense/Conv.

Expected and native arrays are comparison-only files, never DDR inputs. The
normalization is the explicit raw-input boundary and is not claimed as DUT.
"""
from pathlib import Path
import argparse
import hashlib
import inspect
import json
import math
import os
import resource
import tempfile
import time
import weakref
import numpy as np
from host_bf16_gdn_descriptor import *
from host_bf16_qkv_reference import _compile_matrix, _project_and_crosscheck, _tool_file
from heteronpu.pinned_gdn_payload import load_payload as load_gdn
from heteronpu.pinned_prefix_payload import load_payload as load_prefix, token_fixture
from heteronpu.matrix_norm_rope_candidate import compare_native

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / 'chisel/continuous_prefill/config/host_bf16_gdn_descriptor_contract.json'
MODEL_REVISION = '2fc06364715b967f1860aea9cf38778875588b17'
FRAMEWORK_REVISION = '14e738b5d0cc69aa27a95dde272aea41fde44f2f'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def require(ok, why):
    if not ok: raise ValueError(why)
def bf16(x):
    u = np.ascontiguousarray(x, dtype='<f4').view('<u4')
    return ((u + 0x7fff + ((u >> 16) & 1)) >> 16).astype('<u2')
def fp(x): return (np.asarray(x, dtype='<u2').astype('<u4') << 16).view('<f4')


def conv_recipe(inputs, weights, past, cold):
    """Frozen GdnConv4TestSupport recipe, separate FP32 rounding at each step."""
    require(inputs.shape == (1, CHANNELS) and weights.shape == (CHANNELS, TAPS) and past.shape == weights.shape, 'Conv recipe geometry')
    f = np.float32
    history = np.zeros_like(past) if cold else past.copy()
    history[:, :-1] = history[:, 1:]; history[:, -1] = inputs[0]
    acc = np.zeros(CHANNELS, dtype='<f4')
    for k in range(4): acc = np.add(acc, np.multiply(fp(history[:, k]), fp(weights[:, k]), dtype=np.float32), dtype=np.float32)
    conv = bf16(acc); x = fp(conv)
    require(np.isfinite(x).all() and np.all(x > -80), 'unsupported Conv/SiLU numerical domain')
    magnitude = np.abs(x)
    t = np.multiply(magnitude, f(1 / math.log(2)), dtype=np.float32)
    k = t.astype(np.int32); fraction = np.subtract(t, k.astype(np.float32), dtype=np.float32)
    coefficients = [f((-math.log(2)) ** i / math.factorial(i)) for i in range(8)]
    h = np.full(CHANNELS, coefficients[7], dtype='<f4')
    for i in range(6, -1, -1): h = np.add(np.multiply(h, fraction, dtype=np.float32), coefficients[i], dtype=np.float32)
    scale = ((127 - np.minimum(k, 126)).astype('<u4') << 23).view('<f4')
    exp = np.where(magnitude >= 80, f(0), np.multiply(h, scale, dtype=np.float32)).astype('<f4')
    inv = np.divide(f(1), np.add(f(1), exp, dtype=np.float32), dtype=np.float32)
    sigmoid = np.multiply(inv, np.where(np.signbit(x), exp, f(1)), dtype=np.float32)
    output = bf16(np.multiply(sigmoid, x, dtype=np.float32))
    return conv.reshape(1, CHANNELS), output.reshape(1, CHANNELS), history


def ulp_metric(actual, native, limit=1):
    require(actual.shape == native.shape, 'native comparison geometry')
    a, b = actual.astype(np.int32), native.astype(np.int32)
    # Fold both zero encodings to the same ordered integer position.
    ordered = lambda x: np.where(x & 0x8000, 0x8000 - (x & 0x7fff), 0x8000 + x)
    ulp = np.abs(ordered(a) - ordered(b))
    return dict(elements=int(a.size), bit_mismatches=int(np.count_nonzero(a != b)), numeric_mismatches=int(np.count_nonzero(ulp)),
                max_bf16_ulp=int(ulp.max()), signed_zero_numeric_equal=True, threshold_bf16_ulp=limit, pass_=bool(ulp.max() <= limit))


def _sources():
    paths = [Path(__file__).resolve(), Path(__file__).with_name('host_bf16_gdn_descriptor.py'),
             Path(__file__).with_name('host_bf16_qkv_reference.py'), CONTRACT,
             ROOT / 'src/heteronpu/pinned_prefix_payload.py', ROOT / 'src/heteronpu/pinned_gdn_payload.py',
             ROOT / 'src/heteronpu/matrix_norm_rope_candidate.py', ROOT / 'src/heteronpu/rope_bf16_candidate.py',
             ROOT / 'scripts/matrix_norm_rope_reference.c',
             ROOT / 'config/model_profiles/qwen3_5_0p8b.json',
             ROOT / 'config/upstream/qwen3_5_0p8b/config.json',
             ROOT / 'config/upstream/qwen3_5_0p8b/prefix_token_fixture.json',
             ROOT / 'config/upstream/qwen3_5_0p8b/prefix_payload_pin.json',
             ROOT / 'config/upstream/qwen3_5_0p8b/layer0_payload_pin.json',
             ROOT / 'chisel/continuous_prefill/src/test/scala/heteronpu/continuous/GdnConv4OwnerSpec.scala']
    return {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths}


_ISSUED = weakref.WeakKeyDictionary()
class GdnFixtureSession:
    """Live same-invocation authority; saved caller hashes cannot issue one."""
    __slots__ = ('__weakref__',)
    def __init__(self): raise TypeError('use generate_fixture')
    def verify(self, directory):
        require(self in _ISSUED, 'unissued source authority')
        original, files, manifest = _ISSUED[self]
        directory = Path(directory).resolve()
        require(directory == original and not directory.is_symlink(), 'different source directory')
        require(_sources() == manifest['source_sha256'], 'producer source changed')
        require({p.name for p in directory.iterdir()} == set(files) | {'manifest.json', 'c_matrix'}, 'fixture inventory changed')
        require(all(not p.is_symlink() for p in directory.iterdir()), 'fixture symlink')
        for name, raw in files.items(): require((directory / name).read_bytes() == raw, 'source-bound bytes changed: ' + name)
        require(json.loads((directory / 'manifest.json').read_text()) == manifest, 'manifest changed')
        require(_tool_file(directory / 'c_matrix') == manifest['tools']['executable'], 'reference executable changed')
        return manifest


def generate_fixture(output):
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT / 'work') and output != ROOT / 'work' and not output.exists(), 'fresh ignored work output required')
    import torch
    import torch.nn.functional as F
    from transformers.models.qwen3_5 import modeling_qwen3_5 as official
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    profile = json.loads((ROOT / 'config/model_profiles/qwen3_5_0p8b.json').read_text())
    sourcefile = Path(inspect.getfile(official))
    require(sha(sourcefile.read_bytes()) == profile['transformers_source']['sha256'], 'pinned Transformers source drift')
    config_raw = (ROOT / 'config/upstream/qwen3_5_0p8b/config.json').read_bytes()
    require(sha(config_raw) == profile['config_sha256'], 'config source drift')
    config = json.loads(config_raw)['text_config']
    manifest, raw = load_gdn(ROOT, ROOT / 'work/qwen35_layer0_payload')
    prefix_manifest, prefix = load_prefix(ROOT, ROOT / 'work/qwen35_prefix_payload')
    require(manifest['revision'] == prefix_manifest['revision'] == MODEL_REVISION, 'checkpoint revision drift')
    tokens = token_fixture(ROOT)['token_ids'][:2]
    tensor = lambda data, shape: torch.frombuffer(bytearray(data), dtype=torch.bfloat16).reshape(shape)
    word = lambda t: t.detach().contiguous().view(torch.int16).numpy().view('<u2').copy()
    embeddings = tensor(prefix['embed_tokens.rows_0_255'], (256, 1024))[tokens].unsqueeze(0)
    norm = official.Qwen3_5RMSNorm(1024, eps=config['rms_norm_eps']).to(torch.bfloat16)
    norm.weight.data.copy_(tensor(raw['input_layernorm.weight'], (1024,)))
    native_weight = tensor(raw['linear_attn.in_proj_qkv.weight'], (CHANNELS, HIDDEN))
    conv_weight = tensor(raw['linear_attn.conv1d.weight'], (CHANNELS, TAPS))
    with torch.inference_mode():
        normalized = norm(embeddings)
        native_projection = torch.cat([F.linear(normalized[:, i:i + 1], native_weight) for i in range(2)], dim=1)
        native_state = torch.zeros((1, CHANNELS, TAPS), dtype=torch.bfloat16)
        native_outputs, native_histories, native_convs = [], [], []
        for token in range(2):
            x = native_projection[:, token:token + 1].transpose(1, 2)
            native_convs.append(word(F.conv1d(torch.cat([native_state, x], dim=-1), conv_weight.unsqueeze(1), groups=CHANNELS)[:, :, -1:].transpose(1, 2))[0])
            if token == 0:
                y = official.causal_conv1d_fn(x, conv_weight, activation='silu')
                native_state[:, :, -1:] = x
            else: y = official.causal_conv1d_update(x, native_state, conv_weight, activation='silu')
            native_outputs.append(word(y.transpose(1, 2))[0]); native_histories.append(word(native_state)[0])
    activation = word(normalized)[0]
    weights = np.ascontiguousarray(np.frombuffer(raw['linear_attn.in_proj_qkv.weight'], dtype='<u2').reshape(CHANNELS, HIDDEN).T)
    cw = np.frombuffer(raw['linear_attn.conv1d.weight'], dtype='<u2').reshape(CHANNELS, TAPS)
    del prefix
    output.mkdir(parents=True)
    executable, tools = _compile_matrix(output)
    files, heads, canonical = {}, [], []
    def write(name, data): files[name] = bytes(data); (output / name).write_bytes(data)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='.gdn_head_', dir=output) as tmp:
        for token in range(2):
            parts = []
            for head in range(CHANNELS // 256):
                selected = np.ascontiguousarray(weights[:, head * 256:(head + 1) * 256])
                values, receipt = _project_and_crosscheck(activation[token], selected, executable, Path(tmp))
                heads.append(dict(token=token, head=head, activation_sha256=sha(activation[token].tobytes()), weight_sha256=sha(selected.tobytes()), c_reference=receipt))
                parts.append(values['bf16'])
                print(f'GDN_REFERENCE token={token} head={head} pass=1 elapsed={time.monotonic()-started:.1f}', flush=True)
            canonical.append(np.frombuffer(b''.join(parts), dtype='<u2').copy().reshape(1, CHANNELS))
    require(len(heads) == 48 and sum(h['c_reference']['matrix_accumulator_steps'] for h in heads) == 12582912, 'bounded oracle coverage')
    history = np.zeros((CHANNELS, TAPS), dtype='<u2')
    metrics = []
    for token in range(2):
        conv, out, history = conv_recipe(canonical[token], cw, history, token == 0)
        with torch.inference_mode():
            x = tensor(canonical[token].tobytes(), (1, 1, CHANNELS)).transpose(1, 2)
            prev = np.zeros_like(history) if token == 0 else np.frombuffer(files['expected_history0.bf16le'], dtype='<u2').reshape(CHANNELS, TAPS)
            state = tensor(prev.tobytes(), (1, CHANNELS, TAPS))
            official_conv = F.conv1d(torch.cat([state, x], dim=-1), conv_weight.unsqueeze(1), groups=CHANNELS)[:, :, -1:]
            official_out = official.causal_conv1d_fn(x, conv_weight, activation='silu') if token == 0 else official.causal_conv1d_update(x, state, conv_weight, activation='silu')
        conditioned_conv = word(official_conv.transpose(1, 2))[0]
        conditioned_out = word(official_out.transpose(1, 2))[0]
        metrics.append(dict(token=token, projection=compare_native(canonical[token], word(native_projection)[0, token:token + 1]),
                            conv_same_canonical_input=ulp_metric(conv, conditioned_conv),
                            silu_same_canonical_input=ulp_metric(out, conditioned_out),
                            end_to_end_conv=compare_native(conv, native_convs[token]),
                            end_to_end_silu=compare_native(out, native_outputs[token]),
                            end_to_end_conv_ulp=ulp_metric(conv, native_convs[token]),
                            end_to_end_silu_ulp=ulp_metric(out, native_outputs[token])))
        for name, a in [('activation', activation[token]), ('independent_dense', canonical[token]),
                        ('expected_conv', conv), ('expected_output', out), ('expected_history', history),
                        ('native_dense', word(native_projection)[0, token]), ('native_conv', native_convs[token]),
                        ('native_output', native_outputs[token]), ('native_history', native_histories[token]),
                        ('conditioned_conv', conditioned_conv), ('conditioned_output', conditioned_out)]:
            write(f'{name}{token}.bf16le', a.tobytes())
    write('weight_dense.bf16le', weights.tobytes()); write('weight_conv.bf16le', cw.tobytes())
    write('initial_history.bf16le', bytes(CHANNELS * TAPS * 2))
    base = 0x120000000; cb = base; db = base + 0x1000; meta = base + 0x2000; cursor = base + 0x10000
    def allocate(size):
        nonlocal cursor
        address = cursor; cursor += (size + 63) // 64 * 64 + 0x1000; return address
    aa = [allocate(2048) for _ in range(2)]; wd = allocate(weights.nbytes); wc = allocate(cw.nbytes); hi = allocate(CHANNELS * TAPS * 2)
    scratch = cursor; cursor += 0x1000
    dense, conv, hist = [], [], []
    for token in range(2):
        dense.append(allocate(CHANNELS * 2)); conv.append(allocate(CHANNELS * 2)); hist.append(allocate(CHANNELS * TAPS * 2))
    bindings = [HostGdnDenseBinding(1, aa[0], wd, dense[0]), HostGdnConvBinding(1, dense[0], wc, conv[0], hi, hist[0], True),
                HostGdnDenseBinding(1, aa[1], wd, dense[1]), HostGdnConvBinding(1, dense[1], wc, conv[1], hist[0], hist[1], False, 1)]
    commands, records = build_gdn_commands(bindings)
    command_bytes = b''.join(c.pack().to_bytes(16, 'little') for c in commands)
    descriptor_bytes = b''.join(records[i].pack().to_bytes(16, 'little') for i in range(len(records)))
    descriptor_bytes += bytes(-len(descriptor_bytes) % 64)
    write('host_commands.bin', command_bytes); write('host_descriptors.bin', descriptor_bytes)
    launch = 'HOST_GDN_DENSE_CONV_V1\n' + ' '.join(map(str, [base, cursor, cb, cb + len(command_bytes), 4, db, db + len(descriptor_bytes), len(records), meta, scratch, wd, wc, hi])) + '\n'
    for pc, (b, c) in enumerate(zip(bindings, commands)):
        is_dense = pc % 2 == 0
        launch += ' '.join(map(str, [pc // 2, int(is_dense), b.activation_ddr, b.weight_ddr, b.output_ddr,
                                    0 if is_dense else b.history_input_ddr, 0 if is_dense else b.history_output_ddr,
                                    DENSE_RECORDS if is_dense else CONV_RECORDS, c.event_wait, c.event_signal, c.dst])) + '\n'
    write('launch.txt', launch.encode())
    report = dict(schema_version=1, status='SOURCE_AUTHENTICATED_HOST_GDN_TWO_TOKEN_FIXTURE', scope='DENSE_QKV_CONV4_SILU_ONLY',
                  input_boundary='pinned real embedding tokens0/1 -> official layer0 inputNorm; inputNorm is not DUT', token_ids=tokens,
                  model_id=manifest['model_id'], model_revision=MODEL_REVISION, framework_revision=FRAMEWORK_REVISION, framework_source_sha256=sha(sourcefile.read_bytes()),
                  torch_version=torch.__version__, numpy_version=np.__version__, python_version=os.sys.version,
                  tools=tools, source_sha256=_sources(), heads=heads, head_jobs=48, matrix_accumulator_steps=12582912,
                  token_fixture_sha256=sha((ROOT / 'config/upstream/qwen3_5_0p8b/prefix_token_fixture.json').read_bytes()),
                  input_embedding_sha256=sha(word(embeddings).tobytes()), embedding_rows_sha256=prefix_manifest['tensors'][0]['sha256'],
                  layer0_all14_weight_sha256={t['local_name']:t['sha256'] for t in manifest['tensors']},
                  source_payload_manifest_sha256={name:sha((ROOT / 'work' / name / 'manifest.json').read_bytes()) for name in ('qwen35_layer0_payload','qwen35_prefix_payload')},
                  native_metrics=metrics, native_gate_pass=all(m['projection']['pass'] and m['conv_same_canonical_input']['pass_'] and m['silu_same_canonical_input']['pass_'] and m['end_to_end_conv']['pass'] and m['end_to_end_silu']['pass'] for m in metrics),
                  files={name:dict(bytes=len(raw), sha256=sha(raw)) for name, raw in files.items()},
                  commands=4, descriptor_records=60, events=[[i,i+1] for i in range(4)], expected_dma_write_bytes=147456,
                  expected_publication_spans=6, generations=[0,1,2], full_prefix_executed=False, full128_reference_generated=False,
                  max_head_trace_bytes=1024*256*4, reference_elapsed_seconds=time.monotonic()-started, max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  intermediate_ddr_initialization='sentinel only; actual accepted DMA writes are the sole consumers source',
                  native_full_block_gate_pass=None, native_full_block_status='NOT_EVALUATED_BY_THIS_BOUNDED_PREFIX',
                  full_block_supported=False, recurrent_ssm_supported=False, normalization_supported=False)
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    session = object.__new__(GdnFixtureSession); _ISSUED[session] = (output, files, report)
    session.verify(output)
    return session


def pack_fixture(output): return generate_fixture(output)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('output', type=Path); args = p.parse_args()
    session = generate_fixture(args.output)
    report = session.verify(args.output)
    print(json.dumps({k:report[k] for k in ('status','native_gate_pass','native_metrics','head_jobs','max_rss_kib')}, indent=2))
    require(report['native_gate_pass'], 'native operator gate failed; thresholds unchanged')
