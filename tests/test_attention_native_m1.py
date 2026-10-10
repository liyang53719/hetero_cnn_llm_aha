"""Control/identity tests only; no model, payload download, compiler or RTL."""
from pathlib import Path
import copy
import importlib.util
import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('native_m1', ROOT / 'scripts/verify_attention_native_m1.py')
m1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m1)


def words(value):
    return (np.asarray(value, dtype='<f4').view('<u4') >> 16).astype('<u2').tobytes()


def small_bundle():
    files, nodes = {}, {}
    for pos, phase in enumerate(m1.SOURCES):
        files['input/' + phase + '_hidden.bf16le'] = words(np.full((1, 1, 1024), pos + 1, dtype='<f4'))
        files['reference/' + phase + '/rope_q.bf16le'] = words(np.zeros((1, 8, 1, 256), dtype='<f4'))
        for role, value in [('k', 1), ('v', 2)]:
            files['reference/' + phase + '/cache_' + role + '.bf16le'] = words(np.full((pos + 1, 2, 256), value, dtype='<f4'))
        nodes[phase] = {i: np.zeros(m1.producer_shape(i, pos), dtype='<f4') for i in range(57)}
    files['input/trig.bf16le'] = bytes(256)
    failures = {'baseline': {'gate_pass': False, 'failed_producers': ['old-failure']},
                'avx2': {'gate_pass': False, 'failed_producers': ['another-old-failure']}}
    return dict(files=files, nodes=nodes, reference_receipt_file_sha256='f' * 64,
                reference_receipt_sha256='c' * 64,
                receipt={'original_native_full_block_failures': failures, 'inputs': {}})


class FakeOfficial:
    metadata = {'test_adapter': True}

    def __init__(self):
        self.calls, self.gqa_calls = [], []

    def forward(self, hidden, position, prior):
        self.calls.append((hidden.copy(), position, tuple(v.copy() for v in prior)))
        current = tuple(np.concatenate((v, np.full((1, 2, 1, 256), 10 + index, dtype='<f4')), axis=2)
                        for index, v in enumerate(prior))
        return dict(nodes={i: np.zeros(m1.producer_shape(i, position), dtype='<f4') for i in range(57)},
                    output=np.zeros((1, 1, 1024), dtype='<f4'), cache=current,
                    trig=[np.zeros((1, 1, 64), dtype='<f4') for _ in range(2)])

    def conditioned_gqa(self, query, key, value):
        self.gqa_calls.append((query.copy(), key.copy(), value.copy()))
        return {i: np.zeros(m1.producer_shape(i, key.shape[2] - 1), dtype='<f4') for i in range(33, 39)}


def actual_files(bundle, *, same_cache=True):
    files = {}
    for pos, (host, source) in enumerate(zip(m1.PHASES, m1.SOURCES)):
        for name, width in m1.STORED_WIDTHS.items():
            files[host + '/' + name] = bytes(2 * width)
        files[host + '/rope_q'] = bundle['files']['reference/' + source + '/rope_q.bf16le']
        for role, value in [('k', 1), ('v', 2)]:
            files[host + '/cache_' + role] = words(np.full((1, 2, 256), value if same_cache else 5 + value, dtype='<f4'))
            files[host + ('/rope_k' if role == 'k' else '/v')] = files[host + '/cache_' + role]
    return dict(files=files)


def test_limits_keep_hidden_failure_even_when_final_output_passes():
    a, b = np.array([0.04], dtype='<f4'), np.array([0], dtype='<f4')
    assert not m1.stage_metrics(a, b)['pass']
    assert m1.stage_metrics(a, b, block=True)['max_abs_limit'] == .05
    assert not m1.stage_metrics(a, b, block=True)['pass']  # mean also matters
    a = np.array([0.04] + [0] * 9, dtype='<f4'); b = np.zeros(10, dtype='<f4')
    assert not m1.stage_metrics(a, b)['pass']
    assert m1.stage_metrics(a, b, block=True)['pass']
    assert m1.contract()['threshold_source'].startswith('spec/numerical_contract.md')


def test_true_two_m1_calls_keep_official_and_canonical_carry_separate():
    bundle, engine = small_bundle(), FakeOfficial()
    report = m1.audit(bundle, engine)
    assert [v[1] for v in engine.calls] == [0, 1, 0, 1]
    assert all(v[0].shape == (1, 1, 1024) for v in engine.calls)
    assert engine.calls[1][2][0][0, 0, 0, 0] == 10  # official cold result
    assert engine.calls[3][2][0][0, 0, 0, 0] == 1  # canonical prior
    assert report['original_native_full_block_failures'] == bundle['receipt']['original_native_full_block_failures']
    assert not report['native_full_block_acceptance'] and not report['overall_pass']
    assert not report['numerical_rtl_executed']
    assert report['modes']['official_own_cache']['cases'][1]['raw_hidden_sha256'] == m1.digest(bundle['files']['input/cold1_hidden.bf16le'])
    assert report['conditioned_gqa']['carried1']['stages']['33']['origin'] == 'canonical_expected_only'
    assert not report['conditioned_gqa']['carried1']['actual_predecessor_identity_established']


def test_claimed_prior_and_conditioned_qk_use_supplied_bytes_without_hardware_authority():
    bundle, engine = small_bundle(), FakeOfficial()
    actual = actual_files(bundle, same_cache=False)
    report = m1.audit(bundle, engine, actual)
    assert [v[1] for v in engine.calls] == [0, 1, 0, 1, 0, 1]
    assert engine.calls[5][2][0][0, 0, 0, 0] == 6
    assert engine.gqa_calls[1][1].shape == (1, 2, 2, 256)
    assert np.all(engine.gqa_calls[1][1] == 6)
    conditioned = report['conditioned_gqa']['carried1']
    assert not conditioned['actual_predecessor_identity_established']
    assert not conditioned['hardware_authority_verified']
    assert not conditioned['canonical_predecessor_bit_identity']
    assert conditioned['stages']['33']['status'] == 'MISSING_ACTUAL_STAGE_AND_CANONICAL_PREDECESSORS_DIFFER'
    assert conditioned['stages']['38']['origin'] == 'receipt_hashed_claim_only'
    assert 'receipt_hashed_terminal_comparisons' in report['modes']['receipt_claimed_prior_cache']['cases'][1]


def test_claimed_qk_dump_is_distinct_from_canonical_prediction_and_not_hardware_proof():
    bundle, engine = small_bundle(), FakeOfficial()
    actual = actual_files(bundle, same_cache=False)
    actual['files']['carried1/actual_producer_33.f32le'] = np.full((1, 8, 1, 2), .5, dtype='<f4').tobytes()
    report = m1.audit(bundle, engine, actual)
    qk = report['conditioned_gqa']['carried1']['stages']['33']
    assert qk['origin'] == 'receipt_hashed_claim_only'
    assert not qk['hardware_authority_verified']
    assert qk['comparison']['max_abs_error'] == .5 and not qk['comparison']['pass']
    assert not report['native_full_block_acceptance']


def test_same_actual_operands_do_not_invent_actual_internal_readback():
    bundle = small_bundle()
    report = m1.audit(bundle, FakeOfficial(), actual_files(bundle))
    qk = report['conditioned_gqa']['carried1']
    assert qk['canonical_predecessor_bit_identity'] and not qk['actual_predecessor_identity_established']
    assert qk['stages']['33']['origin'] == 'canonical_expected_only'


def test_cache_layout_does_not_mix_tokens_and_heads():
    raw = words(np.arange(2 * 2 * 256, dtype='<f4').reshape(2, 2, 256))
    cache = m1.cache_array(raw, 2)
    assert cache.shape == (1, 2, 2, 256)
    assert cache[0, 1, 0, 0] == 256 and cache[0, 0, 1, 0] == 512
    assert m1.producer_shape(33, 1) == (1, 8, 1, 2)
    with pytest.raises(ValueError, match='two-M1'):
        m1.producer_shape(33, 128)


def test_missing_corrupted_or_symlink_bytes_cannot_recreate_original_pass(tmp_path):
    path = tmp_path / 'original.bf16le'
    with pytest.raises(ValueError, match='missing retained'):
        m1.checked(path, '0' * 64)
    path.write_bytes(b'old')
    with pytest.raises(ValueError, match='hash mismatch'):
        m1.checked(path, m1.digest(b'fresh'))
    link = tmp_path / 'link'; link.symlink_to(path)
    with pytest.raises(ValueError, match='nonsymlink'):
        m1.checked(link, m1.digest(b'old'))


@pytest.mark.parametrize('existing_work', [False, True])
def test_report_guard_accepts_only_fresh_descendant_without_creating_it(tmp_path, monkeypatch, existing_work):
    monkeypatch.setattr(m1, 'ROOT', tmp_path)
    work = tmp_path / 'work'
    if existing_work:
        work.mkdir()
    output = work / 'native_m1' / 'report.json'
    assert m1.fresh_report_path(output) == output
    assert not output.parent.exists()
    assert work.exists() == existing_work


@pytest.mark.parametrize('kind,reason', [
    ('missing', 'fresh report path'),
    ('work_root_absent', 'proper descendant'),
    ('work_root_present', 'fresh nonsymlink'),
    ('outside', 'proper descendant'),
    ('traversal', 'path traversal'),
    ('existing_file', 'fresh nonsymlink'),
    ('existing_directory', 'fresh nonsymlink'),
    ('symlink_file', 'fresh nonsymlink'),
    ('symlink_ancestor', 'fresh nonsymlink'),
    ('dangling_symlink_ancestor', 'fresh nonsymlink'),
    ('file_ancestor', 'ancestors must be directories'),
    ('work_file_ancestor', 'ancestors must be directories'),
])
def test_cli_report_guard_rejects_before_model_execution(tmp_path, monkeypatch, kind, reason):
    monkeypatch.setattr(m1, 'ROOT', tmp_path)
    monkeypatch.setattr(m1, 'load_bundle', lambda *args: small_bundle())
    monkeypatch.setattr(m1, 'OfficialM1', lambda *args: pytest.fail('guard must reject before model construction'))
    work = tmp_path / 'work'
    output = work / 'report.json'
    if kind == 'missing':
        output = None
    elif kind.startswith('work_root_'):
        output = work
        if kind == 'work_root_present': work.mkdir()
    elif kind == 'outside':
        output = tmp_path / 'report.json'
    elif kind == 'traversal':
        output = work / 'nested' / '..' / 'report.json'
    elif kind == 'work_file_ancestor':
        work.write_text('preserve work file')
    else:
        work.mkdir()
        if kind == 'existing_file': output.write_text('preserve report')
        elif kind == 'existing_directory': output.mkdir()
        elif kind == 'symlink_file': output.symlink_to(tmp_path / 'absent.json')
        else:
            ancestor = work / 'ancestor'
            output = ancestor / 'report.json'
            if kind == 'file_ancestor': ancestor.write_text('preserve ancestor')
            elif kind == 'symlink_ancestor': ancestor.symlink_to(tmp_path, target_is_directory=True)
            else: ancestor.symlink_to(tmp_path / 'absent', target_is_directory=True)
    argv = ['verify_attention_native_m1.py', '--bundle', str(tmp_path),
            '--receipt-file-sha256', 'f' * 64, '--execute-official']
    if output is not None:
        argv += ['--output', str(output)]
    monkeypatch.setattr('sys.argv', argv)
    with pytest.raises(ValueError, match=reason):
        m1.main()
    if kind == 'work_root_absent':
        assert not work.exists()
    elif kind == 'existing_file':
        assert output.read_text() == 'preserve report'
    elif kind == 'file_ancestor':
        assert output.parent.read_text() == 'preserve ancestor'
    elif kind == 'work_file_ancestor':
        assert work.read_text() == 'preserve work file'


def test_actual_input_identity_must_match_reference_before_loading_outputs(tmp_path):
    bundle = small_bundle(); bundle['receipt']['inputs'] = {'cold0_hidden.bf16le': {'sha256': '1' * 64}}
    result = dict(actual_dut_identity_verified=True, same_dut_launches=2, resets_between_launches=0,
                  input_sha256={'cold0_hidden.bf16le': '2' * 64})
    path = tmp_path / 'result.json'; path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match='raw input identities differ'):
        m1.load_actual(tmp_path, path, m1.digest(path.read_bytes()), bundle)


def test_retention_plan_counts_exact_bytes_and_excludes_weights():
    plan = m1.retention_plan()
    assert sum(v['bytes'] for v in plan['raw_files'] if 'hidden' in v['path']) == 4096
    assert sum(v['bytes'] for v in plan['raw_files'] if '/actual_' in v['path']) == 137216
    assert plan['raw_bytes'] == 147712
    assert plan['optional_gqa_bytes'] == 480
    assert sum(v['bytes'] for v in plan['optional_gqa_files'] if 'producer_33' in v['path']) == 96
    assert not plan['downloadable_weights_included']
    assert plan['status'] == 'TODO_NOT_CAPTURED' and not plan['native_full_block_acceptance']


def test_cli_retention_plan_cannot_construct_official_model(monkeypatch, capsys):
    monkeypatch.setattr(m1, 'OfficialM1', lambda bundle: pytest.fail('unexpected model construction'))
    monkeypatch.setattr('sys.argv', ['verify_attention_native_m1.py', '--retention-plan'])
    m1.main()
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'TODO_NOT_CAPTURED'
    assert report['raw_bytes'] == 147712


def write_using_actual_fixture_serializer(tmp_path, monkeypatch, receipt):
    """Exercise the production JSON writer; only unrelated payload checks are stubbed."""
    sys.path.insert(0, str(ROOT / 'chisel/continuous_prefill/scripts'))
    import host_bf16_attention_block_fixture as fixture
    from host_bf16_attention_block_live_gate import encoded
    destination = tmp_path / 'reference_bundle'
    with monkeypatch.context() as scoped:
        scoped.setattr(fixture, 'reference_inventory', lambda value: {})
        scoped.setattr(fixture, 'validate_reference_receipt', lambda path, value: {})
        fixture.write_reference_bundle({}, {}, receipt, destination)
    path = destination / 'reference_receipt.json'
    return path, m1.digest(path.read_bytes()), m1.digest(encoded(receipt))


def test_actual_stage_presence_without_execution_hash_is_not_readback_evidence(tmp_path, monkeypatch):
    bundle = small_bundle(); supplied = actual_files(bundle)
    path, file_sha, canonical_sha = write_using_actual_fixture_serializer(tmp_path, monkeypatch, bundle['receipt'])
    parsed, identities = m1.read_reference_receipt(path, file_sha, canonical_sha)
    assert parsed == bundle['receipt'] and file_sha != canonical_sha
    bundle.update(identities)
    outputs = {}; execution = {}
    for phase in m1.PHASES:
        (tmp_path / phase).mkdir()
        outputs[phase] = {}
        for name in m1.STORED_WIDTHS:
            raw = supplied['files'][phase + '/' + name]
            relative = phase + '/actual_' + name + '.bf16le'
            (tmp_path / relative).write_bytes(raw)
            outputs[phase][name] = execution[relative] = m1.digest(raw)
    forged = tmp_path / 'carried1/actual_producer_33.f32le'
    forged.write_bytes(np.full((1, 8, 1, 2), .5, dtype='<f4').tobytes())
    result = dict(actual_dut_identity_verified=True, same_dut_launches=2, resets_between_launches=0,
        input_sha256={}, full_block_artifact_consistency=True, full_block_m1_executed=True,
        live_authorities_verified=True, actual_sha256=outputs, execution_identity={'files_sha256': execution},
        block_reference_receipt_sha256=bundle['reference_receipt_sha256'], mode='pass',
        status='PASS_PRODUCTION_HOST_ATTENTION_BLOCK_PAIR_FROZEN_RECIPE',
        runs=[dict(phase=phase, status=0, checkpoint_accepted=True, inferred_committed_length=i + 1,
                   inferred_committed_generation=i + 1) for i, phase in enumerate(m1.PHASES)])
    path = tmp_path / 'result.json'; path.write_text(json.dumps(result))
    accepted = m1.load_actual(tmp_path, path, m1.digest(path.read_bytes()), bundle)
    assert 'carried1/actual_producer_33.f32le' not in accepted['files']
    execution['carried1/actual_producer_33.f32le'] = m1.digest(forged.read_bytes())
    path.write_text(json.dumps(result))
    accepted = m1.load_actual(tmp_path, path, m1.digest(path.read_bytes()), bundle)
    assert 'carried1/actual_producer_33.f32le' in accepted['files']
    # A caller can forge both file and receipt. Passing their hash consistency
    # checks must never create direct hardware/actual-predecessor authority.
    report = m1.audit(bundle, FakeOfficial(), accepted)
    assert accepted['evidence_status'] == 'receipt_hashed_claim_only'
    assert not accepted['hardware_authority_verified']
    assert not report['hardware_authority_verified'] and not report['native_full_block_acceptance']
    qk = report['conditioned_gqa']['carried1']
    assert not qk['actual_predecessor_identity_established']
    assert qk['stages']['33']['origin'] == 'receipt_hashed_claim_only'
    assert not qk['stages']['33']['hardware_authority_verified']
    assert 'direct_actual' not in json.dumps(report)
    # A terminal's alternate hash field cannot override the physical receipt.
    outputs['cold0']['v'] = 'f' * 64; path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match='physical execution identity differ'):
        m1.load_actual(tmp_path, path, m1.digest(path.read_bytes()), bundle)


def test_reference_receipt_file_and_live_canonical_hashes_are_distinct_contracts(tmp_path, monkeypatch):
    receipt = {'z': {'position': 1}, 'a': [0, 1]}
    path, file_sha, canonical_sha = write_using_actual_fixture_serializer(tmp_path, monkeypatch, receipt)
    assert path.read_bytes() == (json.dumps(receipt, indent=2) + '\n').encode()
    assert file_sha != canonical_sha
    parsed, identities = m1.read_reference_receipt(path, file_sha, canonical_sha)
    assert parsed == receipt
    assert identities == dict(reference_receipt_file_sha256=file_sha, reference_receipt_sha256=canonical_sha)
    with pytest.raises(ValueError, match='hash mismatch'):
        m1.read_reference_receipt(path, canonical_sha)
    with pytest.raises(ValueError, match='canonical reference receipt identity mismatch'):
        m1.read_reference_receipt(path, file_sha, file_sha)


def test_receipt_formatting_and_semantic_drift_have_separate_pins(tmp_path, monkeypatch):
    receipt = {'z': {'position': 1}, 'a': [0, 1]}
    path, file_sha, canonical_sha = write_using_actual_fixture_serializer(tmp_path, monkeypatch, receipt)
    path.write_text(json.dumps(receipt, indent=4) + '\n')
    with pytest.raises(ValueError, match='hash mismatch'):
        m1.read_reference_receipt(path, file_sha, canonical_sha)
    changed_file_sha = m1.digest(path.read_bytes())
    _, identities = m1.read_reference_receipt(path, changed_file_sha, canonical_sha)
    assert identities['reference_receipt_file_sha256'] != file_sha
    assert identities['reference_receipt_sha256'] == canonical_sha
    receipt['z']['position'] = 0
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    with pytest.raises(ValueError, match='canonical reference receipt identity mismatch'):
        m1.read_reference_receipt(path, m1.digest(path.read_bytes()), canonical_sha)


def test_result_canonical_pin_rejects_raw_file_hash(tmp_path, monkeypatch):
    bundle = small_bundle()
    path, file_sha, canonical_sha = write_using_actual_fixture_serializer(tmp_path, monkeypatch, bundle['receipt'])
    _, identities = m1.read_reference_receipt(path, file_sha, canonical_sha)
    bundle.update(identities)
    result = dict(actual_dut_identity_verified=True, same_dut_launches=2, resets_between_launches=0,
                  input_sha256={}, block_reference_receipt_sha256=file_sha)
    result_path = tmp_path / 'result.json'; result_path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match='result/canonical reference receipt mismatch'):
        m1.load_actual(tmp_path, result_path, m1.digest(result_path.read_bytes()), bundle)


def test_cli_inspection_reports_both_receipt_identities(tmp_path, monkeypatch, capsys):
    bundle = small_bundle(); calls = []
    def load(path, file_sha, canonical_sha):
        calls.append((path, file_sha, canonical_sha)); return bundle
    monkeypatch.setattr(m1, 'load_bundle', load)
    monkeypatch.setattr(m1, 'OfficialM1', lambda value: pytest.fail('unexpected model construction'))
    monkeypatch.setattr('sys.argv', ['verify_attention_native_m1.py', '--bundle', str(tmp_path),
        '--receipt-file-sha256', bundle['reference_receipt_file_sha256'],
        '--canonical-receipt-sha256', bundle['reference_receipt_sha256']])
    m1.main()
    report = json.loads(capsys.readouterr().out)
    assert calls == [(tmp_path, bundle['reference_receipt_file_sha256'], bundle['reference_receipt_sha256'])]
    assert report['reference_receipt_file_sha256'] != report['reference_receipt_sha256']
    assert not report['hardware_authority_verified'] and not report['native_full_block_acceptance']


def test_conditioned_trace_excludes_input_conversion_from_six_gqa_producers():
    backend = object.__new__(m1.OfficialM1)
    tracing = [False]; converted = []
    def tensor(value):
        assert not tracing[0], 'input conversion polluted the official producer trace'
        converted.append(value.copy()); return value
    def trace(call, *, conditioned):
        assert conditioned
        tracing[0] = True
        try: call()
        finally: tracing[0] = False
        return None, {33: np.zeros((1, 8, 1, 2), dtype='<f4')}
    backend._tensor, backend._trace = tensor, trace
    backend.torch = SimpleNamespace(bfloat16='bf16', zeros=lambda shape, dtype: np.zeros(shape, dtype='<f4'))
    backend.layer = SimpleNamespace(self_attn='module')
    backend.official = SimpleNamespace(eager_attention_forward=lambda *args, **kwargs: None)
    result = backend.conditioned_gqa(np.zeros((1, 8, 1, 256), dtype='<f4'),
        np.zeros((1, 2, 2, 256), dtype='<f4'), np.zeros((1, 2, 2, 256), dtype='<f4'))
    assert len(converted) == 3 and result[33].shape == (1, 8, 1, 2)


def test_trig_mismatch_rejects_same_input_metrics():
    class DifferentTrig(FakeOfficial):
        def forward(self, hidden, position, prior):
            result = super().forward(hidden, position, prior)
            result['trig'][0][0, 0, 0] = 1
            return result
    with pytest.raises(ValueError, match='same-input comparison rejected'):
        m1.audit(small_bundle(), DifferentTrig())


@pytest.mark.parametrize('mutation,reason', [
    ('model', 'original model revision'), ('schema', 'producer/threshold'),
    ('sources', 'complete original reference source closure'), ('inputs', 'only raw hidden')])
def test_recomputed_receipt_hash_does_not_admit_malformed_source_metadata(tmp_path, mutation, reason):
    sys.path.insert(0, str(ROOT / 'chisel/continuous_prefill/scripts'))
    import host_bf16_attention_block_reference as reference
    c = m1.contract()
    receipt = dict(launch_counts=[1, 1], variant='baseline', model_revision=c['revision'],
        schema=reference.contract_schema(), original_native_thresholds=c['thresholds'],
        source_sha256_before=reference.source_identity(), source_sha256_after=reference.source_identity(),
        status='PREPARED_FULL_BLOCK_EXPECTED_ONLY_NOT_NATIVE_PASS', expected_only=True,
        intermediate_preload_allowed=False, dut_input_injection=False, actual_cache_execution=False,
        numerical_rtl_executed=False, native_full_block_pass=False, full128_reference_generated=False,
        cases={'cold0': {}, 'cold1': {}}, inputs={}, expected={})
    if mutation == 'model': receipt['model_revision'] = 'wrong-model'
    elif mutation == 'schema': receipt['schema']['producer_predecessors']['producer_33'] = {}
    elif mutation == 'sources': receipt['source_sha256_before'] = receipt['source_sha256_after'] = {}
    path = tmp_path / 'reference_receipt.json'; path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match=reason):
        m1.load_bundle(tmp_path, m1.digest(path.read_bytes()))


def test_default_weight_check_rejects_substitute_bytes_without_model():
    with pytest.raises(ValueError, match='original model parameter pin mismatch'):
        m1.validated_weight_words({'input/weight_input_norm.bf16le': bytes(2048)})


def test_historical_failure_claims_must_remain_internally_consistent():
    row = dict(case='cold_m128', producer='self_attn|aten.matmul.default|0',
        max_abs_limit=.03125, mean_abs_limit=.005, max_abs_error=.5, mean_abs_error=.001, pass_=False)
    row['pass'] = row.pop('pass_')
    failed = {v: dict(gate_pass=False, status='BLOCKED_BF16_PRODUCER_GATE', report_sha256=v,
                     failed_producers=[row.copy()]) for v in ('baseline', 'avx2')}
    evidence = dict(native_full_block_gate_pass={v: False for v in failed},
        native_full_block_status={v: 'BLOCKED_BF16_PRODUCER_GATE' for v in failed},
        native_audit_report_sha256={v: v for v in failed}, native_full_block_failed_comparisons={v: 1 for v in failed})
    receipt = dict(variant='baseline', original_native_full_block_failures=failed, original_capture_evidence=evidence,
        original_native_report=dict(thresholds=m1.contract()['thresholds'], failed_producers=[row.copy()],
                                    gate_pass=False, status='BLOCKED_BF16_PRODUCER_GATE'))
    m1.validate_native_failure_claims(receipt)  # Consistency only, not origin authentication.
    for change in ('gate', 'drop', 'threshold'):
        altered = copy.deepcopy(receipt)
        target = altered['original_native_full_block_failures']['avx2']
        if change == 'gate': target['gate_pass'] = True
        elif change == 'drop': target['failed_producers'] = []
        else: target['failed_producers'][0]['max_abs_limit'] = 1
        with pytest.raises(ValueError, match='historical failure'):
            m1.validate_native_failure_claims(altered)
