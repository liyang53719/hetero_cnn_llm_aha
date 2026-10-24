"""Five fixed saved-boundary suffix cases; stdlib only, no arithmetic imports."""
import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = 'qwen35_saved_suffix_m128_v1'
NAMES = ('gated_norm', 'o', 'residual_post_norm', 'gate_up', 'final_triplet')
MATRIX_CASES = ('o', 'gate_up', 'final_triplet')
DENSE_STAGES = ('o', 'gate', 'up', 'down')
TRANSPOSES = {'o': {'weight_kn': ('weight_nk', 1024, 2048)},
              'gate_up': {key+'_weight_kn': (key+'_weight_nk', 3584, 1024) for key in ('gate', 'up')},
              'final_triplet': {'weight_kn': ('weight_nk', 1024, 3584)}}
PREFIX = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
ADDRESSES = {
    'gated_norm': dict(core=0x400000, z=0x500000, weight=0x600000, gated_norm=0x700000),
    'o': dict(gated_norm=0x100000, weight_kn=0x400000, o=0xA00000),
    'residual_post_norm': dict(hidden=0x100000, o=0x200000, weight=0x300000,
                               attention_residual=0x400000, post_norm=0x500000),
    'gate_up': dict(post_norm=0x100000, gate_weight_kn=0x400000, up_weight_kn=0xC00000,
                    gate=0x1600000, up=0x1800000),
    'final_triplet': dict(gate=0x100000, up=0x200000, attention_residual=0x300000,
                         weight_kn=0x400000, silu_mul=0xC00000, down=0xD00000,
                         output=0xE00000, prefix=0x1000000),
}


def need(ok, why):
    if not ok:
        raise ValueError(why)


def case(name):
    need(type(name) is str and name in NAMES, 'only five fixed suffix cases admitted')
    spec = json.loads((HERE / 'suffix_pins.json').read_text())
    selected = copy.deepcopy(spec['cases'][name])
    owners = {'gated_norm': ['GdnGatedNormOwner'], 'o': [],
              'residual_post_norm': ['GdnElementwiseOwner', 'GdnRmsNormOwner'],
              'gate_up': [], 'final_triplet': ['GdnElementwiseOwner', 'GdnElementwiseOwner']}[name]
    selected.update(name=name, schema=SCHEMA, limits=spec['limits'], addresses=ADDRESSES[name],
                    git_calls={PREFIX + owner + '.scala': 2 * owners.count(owner) for owner in owners},
                    cleanup_reserve_seconds=30, postflight_reserve_seconds=10,
                    outer_seconds=210, driver_seconds=180, tokens=128)
    return selected


def plan_case(plan):
    selected = case(plan['case'])
    for key in ('schema', 'policy', 'limits', 'addresses', 'stages'):
        need(plan[key] == selected[key], 'fixed suffix configuration mismatch: ' + key)
    for section in ('stage_inputs', 'references'):
        need(set(plan[section]) == set(selected[section]), 'fixed suffix input names: ' + section)
        for name, expected in selected[section].items():
            actual = plan[section][name]
            need(all(actual[k] == expected[k] for k in ('bytes', 'sha256')), 'fixed suffix input pin: ' + name)
            admitted = plan['inputs'].get(actual['path'], {})
            need(all(admitted.get(k) == expected[k] for k in ('bytes', 'sha256')), 'unpinned suffix input: ' + name)
    need(plan['git_source_identity']['expected_calls'] == selected['git_calls'], 'fixed source-identity calls')
    return selected


def complete(summary, actual, selected):
    """Terminal admission only; numerical acceptance belongs to the comparator."""
    stages = selected['stages']
    return (summary.get('status') == 'ISOLATED_SUFFIX_COMPLETE_UNCOMPARED' and
            summary.get('completed_stages') == stages and summary.get('terminal_count') == len(stages) and
            summary.get('block_generation') == 0 and
            all((actual / name / 'STAGE_TERMINAL.json').is_file() and
                (actual / name / 'output.bf16le').stat().st_size == selected['references'][name]['bytes']
                for name in stages))
