"""Explicit small synthetic component smoke; caller sets runtime once here."""
from contextlib import ExitStack
from collections import OrderedDict
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import struct
from unittest import mock

os.environ['HETERO_35B_RUNTIME_PROFILE'] = 'recovery_20261013'
import torch
# These are caller-owned setup, never inside the reference callable.
torch.set_num_threads(1)
torch.set_num_interop_threads(1)
torch.use_deterministic_algorithms(True)
torch.set_float32_matmul_precision('highest')
torch.set_flush_denormal(False)

HERE = Path(__file__).resolve().parent
OUT = Path('work/gated_norm_pinned_smoke')
OUT.mkdir(parents=True,exist_ok=True)
spec = importlib.util.spec_from_file_location('norm_reference_candidate', HERE / 'norm_reference.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
source_fixture_fallback = False


def direct_original(core_raw, z_raw, gamma_raw, tokens):
    (norm_module, activation_module), _ = r._source_ast()
    namespace = dict(torch=torch, nn=torch.nn, Tensor=torch.Tensor, OrderedDict=OrderedDict)
    exec(compile(activation_module, str(r.ROOT / r.ACTIVATIONS), 'exec'), namespace)
    namespace['ACT2FN'] = namespace['ClassInstantier']({'silu': namespace['SiLUActivation']})
    exec(compile(norm_module, str(r.ROOT / r.SOURCE), 'exec'), namespace)
    gamma = torch.frombuffer(bytearray(gamma_raw), dtype=torch.float32)
    with torch.device('meta'):
        model = namespace[r.NORM_CLASS](128, eps=1e-6)
    model.load_state_dict({'weight': gamma}, assign=True)
    core = torch.frombuffer(bytearray(core_raw), dtype=torch.bfloat16).reshape(tokens * 32, 128)
    z = torch.frombuffer(bytearray(z_raw), dtype=torch.bfloat16).reshape(tokens * 32, 128)
    with torch.inference_mode(), torch.autocast('cpu', enabled=False):
        result = model(core, z)
    return r._raw(result)


def repeat_words(words, count, fmt):
    return b''.join(struct.pack(fmt, words[i % len(words)]) for i in range(count))


def run_case(name, tokens):
    if name == 'zero':
        core = bytes(tokens * 8192)
        z = bytes(tokens * 8192)
        gamma = struct.pack('<f', 1.0) * 128
    else:
        core = repeat_words([0, 0x8000, 0x3f80, 0xbf80, 0x3f81, 0x3f00, 0x4100, 0xc120, 0x0080, 1], tokens * 4096, '<H')
        z = repeat_words([0, 0x8000, 0x3f80, 0xbf80, 0x3f00, 0x4120, 0xc120, 0x3c00, 0x0080, 1], tokens * 4096, '<H')
        gamma = b''.join(struct.pack('<I', 0x3f7f0001 + i * 391) for i in range(128))
    with ExitStack() as stack:
        for setter in ('set_num_threads', 'set_num_interop_threads', 'use_deterministic_algorithms',
                       'set_float32_matmul_precision', 'set_flush_denormal'):
            stack.enter_context(mock.patch.object(torch, setter, side_effect=AssertionError('reference called ' + setter)))
        output, identity, intermediate = r.native_norm(core, z, gamma, tokens)
    expected = direct_original(core, z, gamma, tokens)
    assert output == expected
    assert len(intermediate) == 12
    assert all(v['passed'] is None and not v['independent_diagnostic_recomputation'] for v in intermediate.values())
    assert identity['passed'] is None and identity['thresholds'] is None
    assert identity['inputs']['gamma']['dtype'] == 'torch.float32'
    assert identity['inputs']['gamma']['sha256'] == hashlib.sha256(gamma).hexdigest()
    assert intermediate['weighted_fp32']['dtype'] == 'torch.float32'
    assert intermediate['gated_fp32']['dtype'] == 'torch.float32'
    assert intermediate['normalized_bf16']['dtype'] == 'torch.bfloat16'
    if name == 'zero':
        assert output == bytes(tokens * 8192)
    (OUT / f'{name}_m{tokens}_identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    (OUT / f'{name}_m{tokens}_output.bf16').write_bytes(output)
    result = dict(case=name, tokens=tokens, output_bytes=len(output), output_sha256=identity['output_sha256'],
                  unobserved_original_output_equal=output == expected,
                  original_forward_observations=len(intermediate),
                  gamma_f32_words_with_nonzero_low16=sum((w[0] & 65535) != 0 for w in struct.iter_unpack('<I', gamma)),
                  passed=None, thresholds=None, actual_payload=False)
    print(json.dumps(result), flush=True)
    return result


results = [run_case('zero', 1), run_case('varied', 1), run_case('varied', 2)]
# Independent ABI-level check only: both native module wrappers call the same
# F.silu with default inplace=False. It does not substitute for the observed
# original SiLUActivation execution above.
x = torch.tensor([-20.0, -1.0, -0.0, 0.0, 0.001, 1.0, 20.0], dtype=torch.float32)
with torch.inference_mode():
    silu_equivalent = r._raw(torch.nn.SiLU()(x)) == r._raw(torch.nn.functional.silu(x))
assert silu_equivalent
summary = dict(status='SYNTHETIC_DIAGNOSTIC_ONLY', passed=None, thresholds=None,
    no_weights_downloaded=True, no_full_model_loaded=True, no_actual_core_z_provenance_claim=True,
    source_fixture_fallback=source_fixture_fallback, cases=results,
    nn_silu_vs_functional_silu=dict(complete_bytes_equal=silu_equivalent, passed=None,
        description='independent seven-input ABI smoke, not original-forward intermediate',
        nn_silu_forward_source=inspect.getsource(torch.nn.SiLU.forward)))
(Path('work/gated_norm_pinned_smoke_summary.json')).write_text(json.dumps(summary, indent=2) + '\n')
