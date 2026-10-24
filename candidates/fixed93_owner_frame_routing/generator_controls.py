"""One pinned SOURCE/SYNTHETIC nested-generator control differential.

Executes only pinned fixture definitions and exact observer/dispatcher CodeTypes.
No production Attention body, target/model import, native call or evidence read.
Two same-CodeType synthetic generators are interleaved inside one owner tick;
each delegates with yield from to another routed owner generator and receives send.
"""
import argparse
import ast
import hashlib
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXTURE_SHA = '6efa075b85242acf96a71cf4d37d93665f041357712e7301d9a8c3a79d744401'


def need(value, message):
    if not value:
        raise ValueError(message)


def pinned(path, pin):
    raw = path.read_bytes()
    need(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'],
         'size/SHA mismatch before decode/compile: ' + path.name)
    return raw


SYNTHETIC = '''
def _matrix_step(self, slot):
    value = 10 + slot
    hook_matrix_input_fp32 = value
    value += 1
    hook_matrix_input = value
    PROBE(self, sys._getframe(), 'matrix_enter_' + str(slot))
    token = yield None
    value += token
    PROBE(self, sys._getframe(), 'matrix_send_' + str(slot))
    hook_pv_check = value
    value += 2
    hook_pv_pass = value
    yield value
    PROBE(self, sys._getframe(), 'matrix_finish_' + str(slot))
    return value + 3

def _write(self, slot):
    value = 30 + slot
    hook_store_check = value
    value += 1
    hook_store_pass = value
    return value

def _attention(self, slot):
    value = 40 + slot
    hook_qk_check = value
    value += 1
    hook_qk_pass = value
    PROBE(self, sys._getframe(), 'attention_enter_' + str(slot))
    child_result = yield from self._matrix_step(slot)
    value += child_result
    PROBE(self, sys._getframe(), 'attention_after_delegate_' + str(slot))
    hook_score = value
    value += self._write(slot)
    hook_exp = value
    value += 1
    hook_output = value
    yield value
    PROBE(self, sys._getframe(), 'attention_finish_' + str(slot))
    return value + 5

def tick(self):
    value = 0
    hook_memory_accept = value
    left = self._attention(1)
    right = self._attention(2)
    first_left = next(left)
    first_right = next(right)
    sent_left = left.send(7)
    sent_right = right.send(11)
    final_left = next(left)
    final_right = next(right)
    try:
        left.send(None)
    except StopIteration as stop:
        returned_left = stop.value
    try:
        right.send(None)
    except StopIteration as stop:
        returned_right = stop.value
    value = sent_left + sent_right + final_left + final_right
    hook_memory_match = value
    value += returned_left + returned_right
    hook_write_ack = value
    return {'first': (first_left, first_right), 'sent': (sent_left, sent_right),
            'yielded': (final_left, final_right), 'returned': (returned_left, returned_right),
            'total': value}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    manifest_raw = (ROOT / 'SOURCE_MANIFEST.json').read_bytes()
    manifest_hash = hashlib.sha256(manifest_raw).hexdigest()
    need(manifest_hash == args.manifest_sha256, 'parent manifest SHA mismatch before parse')
    manifest = json.loads(manifest_raw)
    pinned(Path(__file__).resolve(), manifest['files']['generator_controls.py'])
    fixture_raw = pinned(ROOT / 'tests.py', manifest['files']['tests.py'])
    need(hashlib.sha256(fixture_raw).hexdigest() == FIXTURE_SHA, 'unexpected fixture revision')
    fixture = {'__name__': 'pinned_synthetic_fixture_definitions', '__file__': str(ROOT / 'tests.py')}
    exec(compile(fixture_raw.decode('utf-8'), str(ROOT / 'tests.py'), 'exec'), fixture)
    sys.addaudithook(fixture['audit'])
    base = args.baseline.resolve()
    for relative, path, section in (
            ('baseline/cached_wholeblock.py', base / 'cached_wholeblock.py', 'test_inputs'),
            ('baseline/narrow_fullblock_attention.py', base / 'narrow_fullblock_attention.py', 'test_inputs'),
            ('overlay/cached_wholeblock.py', ROOT / 'overlay/cached_wholeblock.py', 'files'),
            ('overlay/narrow_fullblock_attention.py', ROOT / 'overlay/narrow_fullblock_attention.py', 'files')):
        pin = manifest[section][relative]
        fixture['PINS'][path.resolve()] = {'bytes': pin['bytes'], 'sha256': pin['sha256']}
    old_w, old_pool, _ = fixture['source'](base / 'cached_wholeblock.py')
    new_w, new_pool, _ = fixture['source'](ROOT / 'overlay/cached_wholeblock.py')
    old_a, _, _ = fixture['source'](base / 'narrow_fullblock_attention.py')
    new_a, _, _ = fixture['source'](ROOT / 'overlay/narrow_fullblock_attention.py')
    proof = fixture['source_proof'](old_a, new_a, old_w, new_w)
    owner_codes = dict(fixture['OWNER_CODES'])
    owner_codes.update({c.co_name: c for c in fixture['code_tree'](compile(SYNTHETIC, '<SYNTHETIC_NESTED_SEND>', 'exec'))
                       if c.co_name in fixture['GROUPS']})
    hook_lines = {}
    for node in ast.walk(ast.parse(SYNTHETIC)):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith('hook_'):
                    hook_lines[target.id[5:]] = node.lineno
    need(set(hook_lines) == {x for group in fixture['GROUPS'].values() for x in group}, 'fourteen synthetic hook labels')
    fixture['OWNER_CODES'] = owner_codes
    fixture['HOOK_LINES'] = hook_lines
    fixture['LABELS'] = {line: label for label, line in hook_lines.items()}
    fixture['LINES'] = types.MappingProxyType({owner_codes[name]: frozenset(hook_lines[x] for x in labels)
                                             for name, labels in fixture['GROUPS'].items()})
    fixture['ALL'] = frozenset(owner_codes[name] for name in (*fixture['GROUPS'], 'public', 'silu_execute'))
    traces = []
    for pool, routed in ((old_pool, False), (new_pool, True)):
        route_groups = {}
        def probe(fx, frame, where):
            if routed:
                need(frame.f_trace is not fx.d.callback, 'retained hook lost local callback: ' + where)
                fixture['closure_cells'](frame.f_trace, frame)
                family = where.split('_', 1)[0]
                slot = where.rsplit('_', 1)[1]
                route_groups.setdefault((family, slot), []).append(frame.f_trace)
                if where.startswith('matrix_send_'):
                    # The outer generator has no body line while yield-from is
                    # delegating send. Inspect its currently live caller route,
                    # not f_trace after a yield has already expired that segment.
                    outer = frame.f_back
                    need(outer is not None and outer.f_code is owner_codes['_attention'] and
                         outer.f_trace is not fx.d.callback, 'outer send segment did not bind fresh route')
                    fixture['closure_cells'](outer.f_trace, outer)
                    route_groups.setdefault(('attention', slot), []).append(outer.f_trace)
        fx = fixture['Fixture'](pool, routed, probe=probe).run()
        need(fx.caught is None and fx.a.error is None and fx.w.failure is None and fx.d.failed is None,
             'nested generator path poisoned: ' + str(fx.evidence()))
        need(len(fx.a.fields) == 25, 'two generators + one tick must deliver 25 hook records')
        need(fx.a.deliveries == fx.profiled, 'original Whole SUPPORT delivery mismatch')
        if routed:
            need(set(route_groups) == {('attention', '1'), ('attention', '2'), ('matrix', '1'), ('matrix', '2')},
                 'interleaved exact-code frame coverage')
            for key, routes in route_groups.items():
                expected_segments = 4 if key[0] == 'attention' else 3
                need(len(routes) == expected_segments and len({id(route) for route in routes}) == expected_segments,
                     'each next/send resumed segment must get a fresh closure: ' + str(key))
            need(len({id(route) for routes in route_groups.values() for route in routes}) == 14,
                 'same-code generator instances shared local closures')
        traces.append(fx)
    old, new = traces
    need(old.evidence() == new.evidence(), 'nested yield-from/send evidence or original results changed')
    need([x for x in old.profiled if x[1] != 'line'] == [x for x in new.profiled if x[1] != 'line'],
         'nested control event deliveries reduced')
    need(len(new.a.deliveries) < len(old.a.deliveries), 'nested nonhook lines did not bypass both listeners')
    expected = {'first': (None, None), 'sent': (21, 26), 'yielded': (99, 106),
                'returned': (104, 111), 'total': 467}
    need(new.values == [expected], 'synthetic send/return arithmetic fixture changed')
    need(not fixture['DENIED'] and 'ctypes' not in sys.modules and
         not any(name.startswith('candidates.') for name in sys.modules), 'forbidden operation')
    print(json.dumps({
        'status': 'PASS_SOURCE_SYNTHETIC_NESTED_GENERATOR_SEND_ONLY',
        'manifest_sha256': manifest_hash, 'fixture_sha256': FIXTURE_SHA,
        'source_proof': proof, 'original_results_each': new.values,
        'control_events_each': len(new.a.controls), 'fieldlike_hook_records_each': len(new.a.fields),
        'baseline_listener_calls': len(old.a.deliveries), 'routed_listener_calls': len(new.a.deliveries),
        'nested_yield_from': True, 'next_send_terminal_return': True,
        'interleaved_same_code_generator_instances': 2, 'distinct_resumed_closures_checked': 14,
        'exact_dispatcher_and_whole_code_types': True,
        'attention_listener_and_fieldlike_records_are_mock': True,
        'whole_counter_is_test_only_by_code_dict_subclass': True,
        'actual_authorized': False, 'M2_executed': False, 'model_or_native_imported': False,
        'input_reference_or_streams_read': False, 'forbidden_attempts': dict(fixture['DENIED']),
    }, sort_keys=True))


if __name__ == '__main__':
    main()
