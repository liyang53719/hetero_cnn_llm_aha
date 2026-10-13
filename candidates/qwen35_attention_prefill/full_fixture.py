"""Authenticated raw L3 inputs and all eleven original BF16 parameters.

Only immutable source bytes and captured trig constants are execution inputs.
Native intermediate values are selected here by metadata, never returned as
owner inputs. No official forward or independent arithmetic is executed.
"""
from .norm_rope import fixture as prefix
from .input_fixture import require, sha


TAIL_WEIGHTS = {
    'o': ('self_attn.o_proj.weight', (1024, 2048)),
    'post_norm': ('post_attention_layernorm.weight', (1024,)),
    'gate': ('mlp.gate_proj.weight', (3584, 1024)),
    'up': ('mlp.up_proj.weight', (3584, 1024)),
    'down': ('mlp.down_proj.weight', (1024, 3584)),
}
WIDTHS = dict(input_norm=1024, packed_q_gate=4096, k=512, v=512,
              q_norm=2048, k_norm=512, raw_gate=2048, q_rope=2048,
              k_rope=512, context=2048, gated_context=2048, o=1024,
              attention_residual=1024, post_norm=1024, gate=3584, up=3584,
              silu_mul=3584, down=1024, output=1024)
MODULES = dict(o='self_attn.o_proj', post_norm='post_attention_layernorm',
               gate='mlp.gate_proj', up='mlp.up_proj', down='mlp.down_proj')


def select_tail_references(manifest, case):
    """Select full physical module outputs, with exact dtype/layout checks."""
    rows = manifest['query_tokens']
    boundaries = case['module_boundaries']
    refs = {role: boundaries[module]['output']['result']['tensor']
            for role, module in MODULES.items()}
    refs.update(
        attention_residual=boundaries['post_attention_layernorm']['input']['args'][0]['tensor'],
        gated_context=boundaries['self_attn.o_proj']['input']['args'][0]['tensor'],
        silu_mul=boundaries['mlp.down_proj']['input']['args'][0]['tensor'],
        output=case['output'])
    for role, key in refs.items():
        record = manifest['tensors'][key]
        require(record['dtype'] == 'BF16' and record['shape'] == [1, rows, WIDTHS[role]]
                and record['bytes'] == rows * WIDTHS[role] * 2,
                'complete tail reference geometry: ' + role)
    return refs


def load_fixture(directory, payload_directory, root=prefix.ROOT):
    from heteronpu.pinned_block_payload import load_payload
    manifest, weights, inputs, identity, extra = prefix.load_fixture(directory, payload_directory, root)
    payload, all_weights = load_payload(root, payload_directory)
    records = {record['local_name']: record for record in payload['tensors']}
    tail = {}
    for role, (name, shape) in TAIL_WEIGHTS.items():
        record = records[name]
        require(record['dtype'] == 'BF16' and record['shape'] == list(shape),
                'tail checkpoint shape/dtype: ' + role)
        captured = manifest['parameters']['layers.3.' + name]
        require(all(record[key] == captured[key] for key in ('shape', 'dtype', 'bytes', 'sha256')),
                'tail capture/checkpoint identity mismatch: ' + role)
        tail[role] = all_weights[name]
        require(len(tail[role]) == record['bytes'] and sha(tail[role]) == record['sha256'],
                'tail checkpoint bytes: ' + role)
    identity['tail_weight_sha256'] = {role: sha(raw) for role, raw in tail.items()}
    identity['tail_references'] = {case['name']: select_tail_references(manifest, case)
                                   for case in manifest['cases']}
    extra['tail_weights'] = tail
    return manifest, weights, inputs, identity, extra
