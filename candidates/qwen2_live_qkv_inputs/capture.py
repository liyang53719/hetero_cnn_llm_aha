"""Optional official AST oracle. Imported only after the explicit capture opt-in."""
from __future__ import annotations

import ast
import copy
import os
from pathlib import Path
import sys

import recipe as R


def capture(root, pins, subset, inputs, out):
    """Execute exactly the pinned 15-node subset, never Attention.forward."""
    R.need(not out.exists(), 'fresh capture output required')
    _, values, subset_sha, _ = R.read_subset(root, pins, subset)
    _, inputs_sha, _ = R.read_inputs(root, pins, inputs, subset, subset_sha)
    nodes = R.official_nodes(root, pins)
    expected = pins['runtime_requirements']
    R.need(list(sys.version_info[:2]) == expected['python_major_minor'], 'Python major/minor pin drift')
    R.need('ATEN_CPU_CAPABILITY' not in os.environ, 'CPU dispatch override refused')
    R.need('torch' not in sys.modules and 'numpy' not in sys.modules,
           'fresh process with no pre-imported Torch/NumPy required')
    os.environ.update(OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='1')
    import numpy as np
    import torch
    from torch import nn
    R.need(np.__version__ == expected['numpy'] and torch.__version__ == expected['torch'] and
           torch.version.git_version == expected['torch_commit'], 'NumPy/Torch runtime pin drift')
    R.need(torch.backends.cpu.get_cpu_capability() == expected['capability'], 'CPU capability pin drift')
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    namespace = {'torch': torch, 'nn': nn}

    def execute(part):
        code = compile(ast.fix_missing_locations(ast.Module(body=copy.deepcopy(part), type_ignores=[])),
                       str(root / R.MODEL_SOURCE), 'exec')
        exec(code, namespace)

    execute(nodes[:4])
    specs = {spec['local_name']: spec for spec in pins['tensors']}

    def tensor(name):
        # Exact BF16 word interpretation, never a float round trip.
        return torch.from_numpy(np.frombuffer(values[name], dtype='<u2').copy()).view(
            torch.bfloat16).reshape(specs[name]['shape'])

    x = tensor('embed_tokens.rows_0_255')[:16].unsqueeze(0).contiguous()
    gamma = tensor('input_layernorm.weight')
    norm = namespace['Qwen2RMSNorm'](1536, eps=1e-6).to(torch.bfloat16).eval()
    norm.weight = nn.Parameter(gamma, requires_grad=False)
    holder = nn.Module()
    holder.hidden_size, holder.num_heads = 1536, 12
    holder.num_key_value_heads, holder.head_dim = 2, 128
    namespace['self'] = holder
    execute(nodes[4:7])
    for letter in 'qkv':
        layer = getattr(holder, letter + '_proj')
        layer.weight = nn.Parameter(tensor('self_attn.' + letter + '_proj.weight'), requires_grad=False)
        layer.bias = nn.Parameter(tensor('self_attn.' + letter + '_proj.bias'), requires_grad=False)
    # Deliberately bounded cache, unlike the original config's 32768. Pins establish
    # only positions0..15 here, not equivalence of complete config/runtime behavior.
    holder.rotary_emb = namespace['Qwen2RotaryEmbedding'](
        128, max_position_embeddings=256, base=1e6).to(torch.bfloat16)
    holder.eval()
    with torch.inference_mode():
        n0 = norm(x)
        namespace['hidden_states'] = n0
        execute(nodes[7:10])
        outputs = {'x': x, 'n0': n0, 'qr': namespace['query_states'],
                   'kr': namespace['key_states'], 'v': namespace['value_states']}
        namespace.update(bsz=1, q_len=16, kv_seq_len=16,
                         position_ids=torch.arange(16, dtype=torch.long).unsqueeze(0))
        execute(nodes[10:13])
        execute(nodes[13:15])
        outputs.update(q=namespace['query_states'], k=namespace['key_states'],
                       cos=namespace['cos'], sin=namespace['sin'])
    raw_outputs, records = {}, {}
    for name, value in outputs.items():
        spec = pins['references'][name]
        R.need(value.dtype == torch.bfloat16 and bool(torch.isfinite(value).all()), 'finite BF16 reference required')
        data = value.float().contiguous().numpy().astype('<f4', copy=False).tobytes()
        R.fields({'shape': list(value.shape), 'bytes': len(data), 'sha256': R.sha(data)},
                 {key: spec[key] for key in ('shape', 'bytes', 'sha256')}, 'reference ' + name)
        raw_outputs[name] = data
        records[name] = {**spec, 'file': name + '.f32le'}
    comparison = R.compare_historical(raw_outputs, pins)
    runtime = {'python_major_minor': list(sys.version_info[:2]), 'python': sys.version,
               'numpy': np.__version__, 'torch': torch.__version__, 'torch_commit': torch.version.git_version,
               'capability': torch.backends.cpu.get_cpu_capability(), 'threads': torch.get_num_threads(),
               'interop_threads': torch.get_num_interop_threads(),
               'deterministic_algorithms': torch.are_deterministic_algorithms_enabled(),
               'torch_build': torch.__config__.show(),
               'torch_build_sha256': R.sha(torch.__config__.show().encode()), 'affinity': sorted(os.sched_getaffinity(0)),
               'environment': {key: os.getenv(key) for key in ('ATEN_CPU_CAPABILITY', 'OMP_NUM_THREADS',
                   'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'PYTHONPATH', 'PYTHONNOUSERSITE')},
               'new_process': True, 'historical_runtime_equivalence_claimed': False}
    R.fields(runtime, expected, 'fresh runtime')
    libraries = {'python': Path(sys.executable).resolve(), 'torch_C': Path(torch._C.__file__),
                 'numpy_multiarray': Path(np._core._multiarray_umath.__file__)}
    for name in ('libtorch_cpu.so', 'libc10.so', 'libtorch_python.so'):
        libraries[name] = Path(torch.__file__).parent / 'lib' / name
    runtime['native_files'] = {name: {'path': str(path.resolve()), 'bytes': path.stat().st_size,
                                    'sha256': R.sha(path.read_bytes())}
                               for name, path in libraries.items()}
    runtime['identity_scope'] = R.RUNTIME_IDENTITY_SCOPE
    R.check_runtime(runtime, pins)
    R.start_output(out)
    for name, data in raw_outputs.items():
        R.write_new(out / (name + '.f32le'), data)
    result = R.report(root, pins, 'capture')
    result.update(status='FRESH_OFFICIAL_AST_PREFIX_CAPTURE_ONLY', subset=subset, inputs=inputs,
                  subset_manifest_sha256=subset_sha, input_ready_sha256=inputs_sha,
                  official_ast_nodes=pins['official_ast_nodes'], outputs=records, runtime=runtime,
                  official_ast_subset_executed=True, old_runtime_identity_claimed=False,
                  posthoc_oracle_only=True, numerical_acceptance_claimed=False,
                  transformers_imported=False, rotary_cache_max_position_embeddings=256,
                  original_config_max_position_embeddings=32768,
                  configuration_equivalence_claimed=False, historical_comparison=pins['historical_comparison'],
                  reference_hash_comparison=comparison, old_raw_archive_read=False)
    R.write_new(out / 'REFERENCE.json', R.json_bytes(result))
    return result
