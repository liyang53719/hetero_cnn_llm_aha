"""Three fixed saved-boundary suffix cases; stdlib only, no arithmetic imports."""
import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = 'qwen35_saved_suffix_m128_v1'
NAMES = ('gated_norm', 'o', 'residual_post_norm')
PREFIX = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
ADDRESSES = {
    'gated_norm': dict(core=0x400000, z=0x500000, weight=0x600000, gated_norm=0x700000),
    'o': dict(gated_norm=0x100000, weight_kn=0x400000, o=0xA00000),
    'residual_post_norm': dict(hidden=0x100000, o=0x200000, weight=0x300000,
                               attention_residual=0x400000, post_norm=0x500000),
}


def need(ok, why):
    if not ok:
        raise ValueError(why)


def case(name):
    need(type(name) is str and name in NAMES, 'only three fixed suffix cases admitted')
    spec = json.loads((HERE / 'suffix_pins.json').read_text())
    selected = copy.deepcopy(spec['cases'][name])
    owners = {'gated_norm': ['GdnGatedNormOwner'], 'o': [],
              'residual_post_norm': ['GdnElementwiseOwner', 'GdnRmsNormOwner']}[name]
    selected.update(name=name, schema=SCHEMA, limits=spec['limits'], addresses=ADDRESSES[name],
                    git_calls={PREFIX + owner + '.scala': 2 for owner in owners},
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
