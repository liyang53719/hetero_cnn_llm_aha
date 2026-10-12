"""Read-only comparison of actual owner observations after accepted terminals.

This module performs no norm, rsqrt, projection, or rotary execution. Layout
conversion only reshapes recorded words and actual memory writeback. Missing
observations never become a passing result. All 35 unexecuted producers remain
explicitly uncovered even if the 22 covered producers satisfy the original gate.
"""
from pathlib import Path

import numpy as np

from .. import input_fixture
from .fixture import ROOT, NORM_FIELDS, load_contract, require, select_case_references, sha
from ...qwen35_gdn_prefill.prefill_bf16_compare import compare_finite_bf16
from heteronpu.qwen35_bf16_reference import producer_compare

NORM_WIDTHS = dict(squares=256, sum=1, mean=1, mean_eps=1, inverse=1,
                   gamma=256, scaled=256, weighted=256, output=256)
ROPE_WIDTHS = dict(cos_product=64, sin_product=64, rotated=64, output=256)
ROLES = {'q_norm': (8, NORM_WIDTHS), 'k_norm': (2, NORM_WIDTHS),
         'q_rope': (8, ROPE_WIDTHS), 'k_rope': (2, ROPE_WIDTHS)}


class IncompleteObservations(ValueError):
    def __init__(self, missing):
        self.missing = missing
        super().__init__('missing actual owner observations: ' + ', '.join(missing))


class ObservationRecorder:
    """Observer callback that refuses duplicate, partial-width or unknown events.

    The callback retains integers only; it does not calculate missing values.
    .events can be supplied to compare_case after the owner's terminal fires.
    """
    def __init__(self, rows, heads, kind):
        require(type(rows) is int and 1 <= rows <= 128 and type(heads) is int and
                heads in (2, 8) and kind in ('norm', 'rope'), 'observer geometry/kind')
        self.rows, self.heads, self.kind = rows, heads, kind
        self.widths = NORM_WIDTHS if kind == 'norm' else ROPE_WIDTHS
        self.events = {}

    def __call__(self, stage, token, head, words):
        require(type(stage) is str and stage in self.widths and type(token) is int and
                0 <= token < self.rows and type(head) is int and 0 <= head < self.heads,
                'observer stage/token/head')
        key = stage, token, head
        require(key not in self.events, 'duplicate actual observation: ' + str(key))
        require(type(words) is tuple and len(words) == self.widths[stage] and
                all(type(word) is int and 0 <= word < 1 << 32 for word in words),
                'complete actual uint32 observation words')
        require(all((word & 0x7f800000) != 0x7f800000 for word in words), 'nonfinite owner observation')
        if self.kind == 'rope' or stage == 'output':
            require(all(word & 0xffff == 0 for word in words), 'materialized BF16 observation required')
        self.events[key] = words


def validate_observations(observations, rows):
    """Assemble only recorded events into token-major arrays; never recompute."""
    require(type(observations) is dict and set(observations) == set(ROLES), 'four actual observer roles')
    arrays, missing = {}, []
    for role, (heads, widths) in ROLES.items():
        events = observations[role]
        require(type(events) is dict, 'observation event mapping: ' + role)
        checked = ObservationRecorder(rows, heads, 'norm' if role.endswith('norm') else 'rope')
        for key, words in events.items():
            require(type(key) is tuple and len(key) == 3, 'observation key shape')
            checked(*key, words)
        arrays[role] = {}
        for stage, width in widths.items():
            absent = [(token, head) for token in range(rows) for head in range(heads)
                      if (stage, token, head) not in checked.events]
            if absent:
                missing.append(f'{role}.{stage}: {len(absent)} of {rows * heads} heads absent')
                continue
            values = [checked.events[stage, token, head] for token in range(rows) for head in range(heads)]
            arrays[role][stage] = np.asarray(values, dtype='<u4').reshape(1, rows, heads, width)
        if 'gamma' in arrays[role]:
            gamma = arrays[role]['gamma'].reshape(-1, 256)
            require(np.all(gamma == gamma[0]), 'actual gamma differs across heads/tokens')
    if missing:
        raise IncompleteObservations(missing)
    return arrays


def _raw_words(raw, rows, heads, width=256):
    require(type(raw) is bytes and len(raw) == rows * heads * width * 2, 'complete actual BF16 writeback shape')
    return np.frombuffer(raw, '<u2').astype('<u4').reshape(1, rows, heads, width) << 16


def _validate_terminals(terminal_evidence, outputs, rows):
    require(type(terminal_evidence) is dict and set(terminal_evidence) == set(ROLES), 'four owner terminal reports')
    require(type(outputs) is dict and {'packed_q_gate', 'raw_gate', *ROLES} <= set(outputs), 'required actual writebacks')
    for role, (heads, _) in ROLES.items():
        _raw_words(outputs[role], rows, heads)
        names = ('q_norm', 'raw_gate') if role == 'q_norm' else (role,)
        expected = rows * heads * 512 * len(names)
        report = terminal_evidence[role]
        owner = report.get('owner', {})
        require(report.get('complete') is True and report.get('status') is None and
                owner.get('status') is None and type(owner.get('accepted', {}).get('owner_results')) is int and
                owner['accepted']['owner_results'] == 1 and
                report.get('output_published') == [True] * len(names) and
                type(report.get('counts', {}).get('ack_bytes')) is int and
                report['counts']['ack_bytes'] == expected and type(owner.get('acknowledged_write_bytes')) is int and
                owner['acknowledged_write_bytes'] == expected,
                'accepted successful owner terminal/publication/ACK evidence: ' + role)
        require(report.get('output_sha256') == [sha(outputs[name]) for name in names],
                'terminal published output hash differs from actual raw: ' + role)
    packed = _raw_words(outputs['packed_q_gate'], rows, 8, 512)
    gate = _raw_words(outputs['raw_gate'], rows, 8)
    require(np.array_equal(gate, packed[..., 256:]), 'raw gate differs from actual packed projection gate half')


def observation_arrays(observations, actual_outputs, rows):
    """Return comparable actual arrays, checking memory/observer identity first."""
    actual = validate_observations(observations, rows)
    result = {}
    for role, (heads, _) in ROLES.items():
        raw = _raw_words(actual_outputs[role], rows, heads)
        require(np.array_equal(raw, actual[role]['output']), 'observer/output writeback mismatch: ' + role)
        if role.endswith('norm'):
            for field in NORM_FIELDS:
                words = actual[role][field]
                result[role + '.' + field] = words[0, 0, 0].copy() if field == 'gamma' else words
            result[role + '.head_major'] = raw.transpose(0, 2, 1, 3).copy()
        else:
            for field in ROPE_WIDTHS:
                result[role + '.' + field] = actual[role][field].transpose(0, 2, 1, 3).copy()
            norm = _raw_words(actual_outputs[role.replace('rope', 'norm')], rows, heads)
            require(np.array_equal(raw[..., 64:], norm[..., 64:]), 'RoPE tail changed from actual norm writeback')
            require(np.array_equal(raw[..., :64], actual[role]['rotated']), 'RoPE rotated/writeback mismatch')
    result['raw_gate'] = _raw_words(actual_outputs['raw_gate'], rows, 8).reshape(1, rows, 2048)
    return result


def _metrics(words, expected, dtype, thresholds):
    require(words.dtype == np.dtype('<u4') and words.shape == expected.shape and words.size > 0,
            'full actual/native shape and dtype')
    require(not np.any((words & 0x7f800000) == 0x7f800000) and
            not np.any((expected & 0x7f800000) == 0x7f800000), 'finite actual/native values')
    actual_float, native_float = words.view('<f4'), expected.view('<f4')
    metrics = producer_compare(actual_float, native_float)
    require((metrics['max_abs_limit'], metrics['mean_abs_limit']) ==
            (thresholds['max_abs'], thresholds['mean_abs']), 'unchanged original operator thresholds')
    if dtype == 'BF16':
        require(not np.any(words & 0xffff) and not np.any(expected & 0xffff), 'unrounded BF16 producer')
        raw, native_raw = ((array >> 16).astype('<u2').tobytes() for array in (words, expected))
        metrics.update(compare_finite_bf16(raw, native_raw))
        metrics['ulp_gate'] = 'diagnostic only; original absolute/mean limits apply'
    else:
        raw, native_raw = words.tobytes(), expected.tobytes()
        metrics.update(max_abs=metrics['max_abs_error'], mean_abs=metrics['mean_abs_error'],
                       bit_mismatches=metrics['bit_different'], max_bf16_ulp=None,
                       ulp_gate='not assigned to FP32 producers', actual_sha256=sha(raw), expected_sha256=sha(native_raw))
    metrics['pass'] = metrics['passed'] = bool(metrics['max_abs'] <= thresholds['max_abs'] and
                                               metrics['mean_abs'] <= thresholds['mean_abs'])
    changed = np.flatnonzero(words.reshape(-1) != expected.reshape(-1))

    def witness(index):
        coord = tuple(int(i) for i in np.unravel_index(index, words.shape))
        return dict(coordinate=list(coord), candidate=float(actual_float[coord]), native=float(native_float[coord]),
                    candidate_word=f'0x{int(words[coord]):08x}', native_word=f'0x{int(expected[coord]):08x}')

    metrics['first_bit_difference'] = witness(int(changed[0])) if changed.size else None
    metrics['worst_error_witness'] = witness(int(np.argmax(np.abs(actual_float.astype(np.float64) -
                                    native_float.astype(np.float64))))) if changed.size else None
    metrics['elements'] = int(metrics['elements'])
    return metrics


def compare_case(case_name, observations, actual_outputs, manifest, capture_directory, *, terminal_evidence, root=ROOT):
    """Compare 22 required producers + five layout/gate checks, read-only.

    terminal_evidence maps the four role names to their genuine driver reports.
    The runner must freeze raw observations/writebacks before calling this. This
    function never writes or overwrites artifacts, even on comparison failure.
    """
    rows, contract = manifest['query_tokens'], load_contract(root)
    cases = [case for case in manifest['cases'] if case['name'] == case_name]
    require(len(cases) == 1, 'one selected capture case')
    refs = select_case_references(manifest, cases[0], contract)
    _validate_terminals(terminal_evidence, actual_outputs, rows)
    sequence = [item['key'] for item in contract['producer_sequence']]
    covered = [key for key in sequence if key in {item['producer_key'] for item in refs.values()}]
    missing = [key for key in sequence if key not in covered]
    report = dict(case=case_name, scope='ACTUAL_OWNER_NORM_ROPE_22_OF_57_PARTIAL_SCOPE',
        total_required_producers=57, computed_required_producers=0, covered_producer_keys=[],
        uncomputed_required_producer_keys=sequence, numerical_thresholds_changed=False,
        full_contract_accepted=False, native_acceptance=False, rtl_executed=False,
        hardware_cycles=None, native_intermediates_injected=False, native_trig_tables_used=True,
        native_intermediates_used_as_execution_inputs=False,
        native_reference_files_read_scope='this comparison call only; capture integrity may already have read files',
        independent_trig_generation=False, position_span=cases[0]['position_span'],
        original_contract_sha256=manifest['contract_sha256'], stages={}, complete=False)
    try:
        arrays = observation_arrays(observations, actual_outputs, rows)
    except IncompleteObservations as error:
        report.update(status='INCOMPLETE_ACTUAL_OBSERVATIONS', missing_observations=error.missing,
                      all_computed_stages_pass=False, native_reference_files_read=False)
        return report
    require(set(arrays) == set(refs), 'actual/reference stage coverage differs')
    provenance = {}
    # First numerical reference read in this call. The fixture loader already
    # integrity-reads the complete capture, including these intermediate files.
    for label, selection in refs.items():
        tensor = selection['tensor']
        raw = input_fixture.read_tensor(capture_directory, manifest, tensor)
        expected = np.frombuffer(raw, '<u2' if selection['dtype'] == 'BF16' else '<u4')
        if selection['dtype'] == 'BF16':
            expected = expected.astype('<u4') << 16
        expected = expected.reshape(selection['shape'])
        metrics = _metrics(arrays[label], expected, selection['dtype'], contract['thresholds']['operator'])
        metrics.update(native_tensor=tensor, shape=selection['shape'], storage_dtype=selection['dtype'],
                       producer_key=selection['producer_key'], thresholds=dict(contract['thresholds']['operator']))
        report['stages'][label] = metrics
        record = manifest['tensors'][tensor]
        provenance[tensor] = dict(file=record['file'], sha256=sha(raw), bytes=len(raw))
    for record in provenance.values():
        raw = (Path(capture_directory) / record['file']).read_bytes()
        require(len(raw) == record['bytes'] and sha(raw) == record['sha256'], 'native reference changed during comparison')
    stages = report['stages']
    producers = sorted((s for s in stages.values() if s['producer_key']), key=lambda s: sequence.index(s['producer_key']))

    def first(predicate):
        stage = next((s for s in producers if predicate(s)), None)
        return None if stage is None else dict(producer_key=stage['producer_key'], native_tensor=stage['native_tensor'],
            storage_dtype=stage['storage_dtype'], max_abs=stage['max_abs'], mean_abs=stage['mean_abs'],
            first_bit_difference=stage['first_bit_difference'], worst_error_witness=stage['worst_error_witness'])

    passed = all(s['passed'] for s in stages.values())
    report.update(status='PASS_22_OF_57_PARTIAL_SCOPE' if passed else 'FAIL_ORIGINAL_NATIVE_THRESHOLDS',
        complete=True, computed_required_producers=22, covered_producer_keys=covered,
        uncomputed_required_producer_keys=missing, all_computed_stages_pass=passed,
        failed_stages=[label for label, stage in stages.items() if not stage['passed']],
        first_changed_producer=first(lambda s: s['bit_mismatches'] != 0),
        first_fp32_difference=first(lambda s: s['storage_dtype'] == 'F32' and s['bit_mismatches'] != 0),
        first_failed_producer=first(lambda s: not s['passed']), native_reference_files_read=True,
        native_reference_provenance=provenance, raw_gate_exact_actual_projection_slice=True,
        actual_observer_matches_writeback=True, actual_rope_tail_unchanged=True,
        all_native_reference_files_unchanged=True,
        observation_sha256={role: {stage: sha(value.tobytes()) for stage, value in fields.items()}
                            for role, fields in validate_observations(observations, rows).items()})
    return report
