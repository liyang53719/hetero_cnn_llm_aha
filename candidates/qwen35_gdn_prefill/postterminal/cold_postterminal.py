"""Root-gated, cold128-only post-terminal diagnostics; never full acceptance.

Development: stdlib-only synthetic tests. No actual invocation is authorized by
this source file. An explicit reviewed terminal handoff and terminal_gate are
mandatory. No owner, native model, full comparison entrypoint, signaling,
recapture, replay, or artifact repair is called here.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import stat
import types
import sys

HERE = Path(__file__).resolve().parent
FULL_COMPARE_SHA = 'a3de68cba35a649e98fa76ce103731a31c90f79c179d8806232b274c933f3ec1'
ORDER = ('input_norm', 'qkv', 'z', 'ab', 'conv_silu', 'prep', 'chunk',
         'gated_norm', 'o', 'attention_residual', 'post_norm', 'gate', 'up',
         'silu_mul', 'down', 'output')
ROLES = (*ORDER, 'conv_before_silu', 'history_staging', 'state_staging')
POLICY_PAIRS = (
    ('arithmetic_seal_schema', 'arithmetic_seal_schema'), ('rms_policy', 'rms_policy'),
    ('projection_policy', 'projection_policy'), ('projection_profile', 'projection_profile'),
    ('vector_policy', 'vector_exception_policy'), ('vector_fatal_mask', 'vector_fatal_mask'),
    ('vector_arithmetic_backend', 'vector_arithmetic_backend'),
    ('scalar_arithmetic_binding', 'scalar_arithmetic_binding'),
    ('chunk_exp_policy', 'chunk_exp_policy'), ('chunk_exp_identity', 'chunk_exp_identity'),
    ('chunk_cumsum_policy', 'chunk_cumsum_policy'), ('chunk_matmul_policy', 'chunk_matmul_policy'))
FINAL_REQUIRED = ('source_unchanged', 'libraries_receipts_fixture_unchanged',
                  'authenticated_inputs_unchanged', 'library_unchanged',
                  'vector_library_unchanged', 'fixture_unchanged')


def need(ok, why):
    if not ok:
        raise ValueError('cold post-terminal: ' + why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def pin_read(record):
    """Only called for admitted metadata or immutable source/reference pins."""
    need(type(record) is dict and digest(record.get('sha256')) and
         type(record.get('bytes')) is int and record['bytes'] >= 0, 'invalid file pin')
    path = Path(record['path'])
    need(path.is_absolute() and not path.is_symlink() and path.is_file() and
         path.resolve() == Path(record.get('resolved', path)), 'missing/aliased pinned file')
    raw = path.read_bytes()
    need(len(raw) == record['bytes'] and sha(raw) == record['sha256'], 'file pin drift: ' + str(path))
    return raw


def verify_plan_inputs(plan):
    """Same path/stat/hash/stability semantics as the frozen launch.verify.

    Read-only, after terminal admission only. The selected compiler symlink is
    permitted only when it resolves to the original pinned target.
    """
    need(type(plan.get('inputs')) is dict and plan['inputs'], 'frozen plan input inventory missing')
    for name, pin in plan['inputs'].items():
        path = Path(name)
        need(path.is_absolute() and str(path.resolve(strict=True)) == pin['resolved'],
             'frozen plan input resolution: ' + name)
        before = path.stat()
        need(stat.S_ISREG(before.st_mode) and type(pin['bytes']) is int and before.st_size == pin['bytes'] and
             digest(pin.get('sha256')), 'frozen plan input extent: ' + name)
        hasher = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1 << 20), b''):
                hasher.update(block)
        need(hasher.hexdigest() == pin['sha256'], 'frozen plan input hash: ' + name)
        after = path.stat()
        need(all(getattr(before, key) == getattr(after, key) for key in
                 ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')),
             'frozen plan input changed while hashing: ' + name)


def bind_plan_policy(identity, plan):
    policy = plan['policy']
    for key in ('rows', 'rms_policy', 'projection_policy', 'vector_exception_policy', 'vector_fatal_mask',
                'chunk_exp_policy', 'chunk_cumsum_policy', 'chunk_matmul_policy'):
        need(type(identity.get(key)) is type(policy[key]) and identity[key] == policy[key],
             'original execution policy differs from frozen PLAN: ' + key)
    need(type(identity.get('vector_arithmetic_backend')) is dict and
         identity['vector_arithmetic_backend'].get('backend') == policy['vector_backend'],
         'original Vector arithmetic backend differs from frozen PLAN')


def admit_cold_metadata(summary, identity, fc, *, full_driver_sha256, evidence_kind='summary'):
    """Pure metadata admission. Never invent output inventory or final seals."""
    need(fc.ORDER == ORDER and fc.ROLES == ROLES and fc.PHASES == ('cold128', 'carried128'),
         'original comparison inventory changed')
    need(type(identity) is dict and type(identity.get('rows')) is int and identity['rows'] == 128,
         'original M128 identity required')
    need(evidence_kind in ('summary', 'progress') and
         summary.get('scope') == 'QWEN35_L0_COMPLETE_TYPED_SOFTWARE_COORDINATOR', 'original coordinator evidence required')
    if evidence_kind == 'summary':
        need(summary.get('identity') == identity and summary.get('status') == 'FAILED',
             'intact original FAILED summary and identical original identity required')
    else:
        need('identity' not in summary and 'status' not in summary,
             'progress must be genuine coordinator report, not a synthetic summary')
    need(summary.get('full_block_executed') is True and summary.get('native_acceptance') is False,
         'genuine software-only execution evidence required')
    need(summary.get('source_initialization') == 'raw_inputs_and_parameters_only_before_launch' and
         summary.get('carried_dependency') == 'preceding_actual_committed_history_and_fp32_state',
         'raw-only source/carried provenance contract missing')
    for left, right in POLICY_PAIRS:
        need(left in summary and right in identity and summary[left] == identity[right],
             'numerical policy differs from prelaunch identity: ' + left)
    for key in (*FINAL_REQUIRED, 'scalar_arithmetic_binding_unchanged', 'chunk_exp_binding_unchanged',
                'output_files_unchanged', 'live_resource_identity_valid'):
        need(key not in summary or summary[key] is True, 'recorded integrity failure: ' + key)
    need(not summary.get('report_error') and not summary.get('identity_read_errors'),
         'recorded coordinator/identity integrity error')
    final = summary.get('final_identity')
    if final is not None:
        need(type(final) is dict and final.get('identity_read_errors') == {} and
             all(final.get(k) is True for k in FINAL_REQUIRED) and
             all(v is True for k, v in final.items() if k != 'identity_read_errors'),
             'original final identity receipt is incomplete or failed')
    if evidence_kind == 'summary':
        need(final is not None, 'FAILED summary missing original final identity receipt')
    for name in ('source_sha256', 'identity_file_sha256', 'input_sha256',
                 'authenticated_input_sha256', 'parameter_sha256'):
        values = identity.get(name)
        need(type(values) is dict and values and all(digest(v) for v in values.values()),
             'original identity hash inventory missing: ' + name)
    need(identity['source_sha256'].get('candidates/qwen35_gdn_prefill/full_driver.py') == full_driver_sha256 and digest(full_driver_sha256),
         'original joint-commit implementation identity missing')
    commands = summary.get('commands')
    need(type(commands) is list and 16 <= len(commands) < 32, '16..31 real ordered terminals required')
    if 'terminal_count' in summary:
        need(type(summary['terminal_count']) is int and summary['terminal_count'] == len(commands),
             'original terminal count contradicts commands')
    expected = [(phase, role) for phase in ('cold128', 'carried128') for role in ORDER]
    need([(c.get('phase'), c.get('role')) for c in commands] == expected[:len(commands)] and
         [c.get('owner_tag') for c in commands] == list(range(1, len(commands) + 1)) and
         all(type(c.get('owner_tag')) is int for c in commands), 'ordered owner tags/roles mismatch')
    cold = commands[:16]
    for index, c in enumerate(cold):
        need(c.get('complete') is True and c.get('terminal_accepted') is True and
             c.get('status', 'missing') is None and c.get('terminal_status', 'missing') is None,
             'cold terminal incomplete/unaccepted/unsuccessful: ' + ORDER[index])
        need(c.get('output_published') is True and c.get('numeric_fault') is None and c.get('vector_fault') is None and
             ('owner' not in c or (type(c['owner']) is dict and c['owner'].get('status', 'missing') is None)),
             'cold receipt contradicts successful output publication: ' + ORDER[index])
        need(type(c.get('block_generation')) is int and c['block_generation'] == int(index == 15) and
             c.get('block_committed') is (index == 15), 'cold final joint commit missing or early commit')
    # These are genuine receipt hashes, NOT manufactured original output_files.
    receipt_hashes = {c['role']: c.get('output_sha256') for c in cold}
    receipt_hashes.update(
        conv_before_silu=cold[4].get('conv_before_silu_observation', {}).get('output_sha256'),
        history_staging=cold[4].get('history_staging_sha256'), state_staging=cold[6].get('state_sha256'))
    need(set(receipt_hashes) == set(ROLES) and all(digest(v) for v in receipt_hashes.values()),
         'all 19 genuine accepted cold owner receipt hashes required')
    records = {role: dict(bytes=fc.byte_extent(role, 128), sha256=receipt_hashes[role]) for role in ROLES}
    files = summary.get('output_files')
    if evidence_kind == 'summary':
        need(type(files) is dict, 'original FAILED summary output_files inventory absent')
    if files is not None:
        cold_names = {fc.filename('cold128', role) for role in ROLES}
        need(type(files) is dict and {name for name in files if name.startswith('cold128.')} == cold_names,
             'exact original cold19 inventory required')
        for role, record in records.items():
            original_record = files[fc.filename('cold128', role)]
            need(type(original_record) is dict and type(original_record.get('bytes')) is int and
                 original_record == record, 'original tensor extent/hash contradicts receipt: ' + role)
    for command in cold:
        need(command.get('output_sha256') == records[command['role']]['sha256'],
             'cold terminal output hash mismatch: ' + command['role'])
    conv, chunk = cold[4], cold[6]
    need(conv.get('staging_complete') is True and chunk.get('staging_complete') is True and
         conv.get('history_staging_sha256') == records['history_staging']['sha256'] and
         chunk.get('state_sha256') == records['state_staging']['sha256'], 'cold staging receipts incomplete')
    observation = conv.get('conv_before_silu_observation', {})
    need(observation.get('complete') is True and
         observation.get('output_sha256') == records['conv_before_silu']['sha256'] and
         type(observation.get('observed')) is int and type(observation.get('expected')) is int and
         observation['observed'] == observation['expected'] == 128 * 6144 and
         observation.get('source') == 'actual_ConvOwner_readonly_node_callback' and
         observation.get('numerical_replacement') is False, 'genuine complete cold pre-SiLU observation missing')
    need(conv.get('cold_history_initialization') == 'internal_bf16_positive_zero' and
         conv.get('history_input_consumed') is False and conv.get('history_committed') is False and
         conv.get('generation_advanced') is False and chunk.get('state_committed') is False and
         chunk.get('history_committed') is False and chunk.get('generation_advanced') is False,
         'staging owners independently committed or cold history not genuine')
    roots = summary.get('roots', {})
    need(type(roots.get('generation')) is int and roots['generation'] == 1 and
         all(type(roots.get(k)) is int and roots[k] > 0 and roots[k] % 64 == 0
             for k in ('history', 'state', 'output')) and
         len({roots[k] for k in ('history', 'state', 'output')}) == 3 and
         roots.get('history_sha256') == records['history_staging']['sha256'] and
         roots.get('state_sha256') == records['state_staging']['sha256'],
         'retained generation1 roots/hash/pointers invalid')
    response = summary.get('response')
    if response is not None:
        need(type(response) is dict and type(response.get('generation')) is int and
             response['generation'] == 1 and all(response.get(k) == roots[k] for k in ('history', 'state')),
             'generation1 response/root pointer mismatch')
        if response.get('status', 'missing') is None:
            need(response.get('phase') == 'cold128' and response.get('output') == roots['output'],
                 'successful response differs from cold committed output')
        else:
            need(response.get('phase') == 'carried128' and response.get('output') is None,
                 'failed carried response pretends to commit output')
    windows = summary.get('window_inputs')
    need(type(windows) is list and len(windows) == 2 and
         all(type(w.get('cold')) is bool and type(w.get('expected_generation')) is int for w in windows),
         'window admission exact bool/int types required')
    need(windows == [
        dict(phase='cold128', cold=True, expected_generation=0, history_sha256=None, state_sha256=None),
        dict(phase='carried128', cold=False, expected_generation=1,
             history_sha256=records['history_staging']['sha256'], state_sha256=records['state_staging']['sha256'])],
         'original carried input binding to committed cold roots absent')
    return records



def check_companion_summary(companion, evidence, identity, fc, *, full_driver_sha256):
    """An intact later failure cannot be hidden by choosing an older progress pin."""
    need(type(companion) is dict and companion.get('scope') == evidence.get('scope'),
         'missing original whole-run summary')
    if companion.get('status') == 'RUNNING':
        need(set(companion) == {'scope', 'status', 'rows', 'public_command128_executed', 'rtl_executed'} and
             type(companion.get('rows')) is int and companion['rows'] == 128 and companion.get('public_command128_executed') is False and
             companion.get('rtl_executed') is False, 'RUNNING companion is not the original minimal placeholder')
        return
    admit_cold_metadata(companion, identity, fc, full_driver_sha256=full_driver_sha256, evidence_kind='summary')
    need(companion['commands'][:16] == evidence['commands'][:16] and
         companion['roots'] == evidence['roots'] and companion['window_inputs'] == evidence['window_inputs'],
         'original progress and terminal summary contradict cold commit provenance')


def cold_metrics(fc, values, tensors, weights, *, root, include_conv=False):
    """Use original mapping/metrics. Do not modify PHASES or call compare_run."""
    nodes = {}
    for role in (*ORDER, 'history_staging', 'state_staging'):
        if role == 'prep':
            nodes[role] = fc.prep_diagnostic(values[role], tensors, 'cold128', 128)
            need(nodes[role].get('passed') is None and nodes[role].get('thresholds') is None,
                 'packed prep acquired a gate')
            continue
        try:
            expected = fc.native_role(tensors, 'cold128', role, 128)
            nodes[role] = (fc.state_metric(values[role], expected) if role == 'state_staging'
                           else fc.bf16_metric(values[role], expected,
                                               gate='output' if role == 'output' else 'node'))
        except fc.MissingNode as error:
            nodes[role] = fc.missing_metric(error, values[role])
    operators = {role: nodes[role] for role in ('qkv', 'z', 'ab')}
    operators['end_to_end_silu'] = nodes['conv_silu']
    conv_identity = None
    if include_conv:
        try:
            pure, pure_id = fc.captured_conv_reference(tensors, 'cold128', 128,
                weights['linear_attn.conv1d.weight'], root=root)
            conditioned, conditioned_id = fc.conv_reference.native_conv(values['qkv'],
                weights['linear_attn.conv1d.weight'], 128, history_raw=None, root=root)
            operators['end_to_end_conv'] = fc.bf16_metric(values['conv_before_silu'], pure)
            operators['conv_same_actual_input'] = fc.bf16_metric(values['conv_before_silu'], conditioned['conv'], gate='ulp')
            operators['silu_same_actual_input'] = fc.bf16_metric(values['conv_silu'], conditioned['silu'], gate='ulp')
            conv_identity = dict(original_input=pure_id, same_actual_input=conditioned_id)
        except fc.MissingNode as error:
            for name in ('end_to_end_conv', 'conv_same_actual_input', 'silu_same_actual_input'):
                operators.setdefault(name, fc.missing_metric(error))
    else:
        for name in ('end_to_end_conv', 'conv_same_actual_input', 'silu_same_actual_input'):
            operators[name] = dict(status='NOT_RUN_UNSELECTED', passed=None, thresholds=None,
                                   reason='Original Conv reference arithmetic was not selected.')
    return dict(checks=nodes, node_gates_passed=fc.assigned_pass(nodes, prep_unassigned=True),
                operator_checks=operators,
                operator_gates_passed=fc.assigned_pass(operators) if include_conv else None,
                conv_reference_identity=conv_identity)


def check_code(path, reviewed_sha):
    """Verify the exact adapter inventory before any sibling source executes."""
    path = Path(path)
    need(path.is_absolute() and not path.is_symlink() and path.resolve(strict=True) == path,
         'unaliased adapter pins path required')
    before = path.stat()
    need(0 < before.st_size <= 65536 and digest(reviewed_sha), 'invalid reviewed adapter pins')
    raw = path.read_bytes()
    after = path.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    need(sha(raw) == reviewed_sha and all(getattr(before, k) == getattr(after, k) for k in fields),
         'reviewed adapter pins changed')
    pins = json.loads(raw)
    need(type(pins) is dict and set(pins) == {'cold_postterminal.py', 'terminal_gate.py', 'launch_cold.py'},
         'exact adapter code inventory')
    for name, value in pins.items():
        need(type(value) is dict and set(value) == {'bytes', 'sha256'} and
             type(value['bytes']) is int and 0 < value['bytes'] <= 2 << 20 and digest(value['sha256']),
             'invalid adapter source pin: ' + name)
        codepath = HERE / name
        need(not codepath.is_symlink() and codepath.resolve(strict=True) == codepath,
             'adapter source path alias: ' + name)
        before = codepath.stat()
        code = codepath.read_bytes()
        after = codepath.stat()
        need(len(code) == value['bytes'] and sha(code) == value['sha256'] and
             all(getattr(before, k) == getattr(after, k) for k in fields), 'adapter source changed: ' + name)
    return pins


def _load_gate(pins):
    # Compile the verified bytes, not an import-cache or bytecode substitute.
    path = HERE / 'terminal_gate.py'
    raw = path.read_bytes()
    need(not path.is_symlink() and path.resolve(strict=True) == path and
         len(raw) == pins[path.name]['bytes'] and sha(raw) == pins[path.name]['sha256'],
         'terminal gate source/origin mismatch')
    module = types.ModuleType('reviewed_local_terminal_gate')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    need(Path(module.__file__) == path and module.admit_terminal_manifest.__code__.co_filename == str(path),
         'terminal gate import origin mismatch')
    return module


def _local_terminal_gate(reviewed_code_sha):
    return _load_gate(check_code(HERE / 'CODE_PINS.json', reviewed_code_sha))


def _admit_gate(manifest, reviewed_sha, config_path, reviewed_config_sha, reviewed_code_sha):
    return _local_terminal_gate(reviewed_code_sha).admit_terminal_manifest(
        manifest, reviewed_sha, config_path=config_path, reviewed_config_sha=reviewed_config_sha)


def _recheck_gate(gate, reviewed_code_sha):
    return _local_terminal_gate(reviewed_code_sha).recheck_terminal_manifest(gate)


def run_diagnostic(manifest, reviewed_sha, output, *, config_path, reviewed_config_sha,
                   reviewed_code_sha, include_conv=False):
    # After reviewed adapter bootstrap, admission MUST precede actual metadata,
    # tensors, reference tensors, model imports and output filesystem access.
    gate = _admit_gate(manifest, reviewed_sha, config_path, reviewed_config_sha, reviewed_code_sha)
    config = gate['config']
    root, harness = config['paths']['repository'], config['paths']['harness']
    source_commit = config['source_commit']
    plan_sha = config['files']['plan']['sha256']
    native_sha = config['files']['native_manifest']['sha256']
    full_driver_sha = config['full_driver_sha256']
    need(gate['source_commit'] == source_commit and gate['plan_sha256'] == plan_sha and
         gate['whole_run_status'] in ('FAILED', 'INCOMPLETE', 'UNKNOWN'), 'wrong original run or whole-run status')
    need(not include_conv or gate['manifest'].get('include_conv_reference_arithmetic') is True,
         'Conv reference arithmetic lacks explicit reviewed handoff permission')
    metadata = gate['metadata_files']
    evidence_kind = gate['evidence_kind']
    need((evidence_kind == 'summary' and set(metadata) == {'identity', 'summary'}) or
         (evidence_kind == 'progress' and set(metadata) == {'identity', 'progress', 'summary'}),
         'explicit original evidence and companion summary pins required')
    original = {k: pin_read(v) for k, v in metadata.items()}
    summary, identity = json.loads(original[evidence_kind]), json.loads(original['identity'])
    actual_dir = Path(gate['actual_directory'])
    output = Path(output)
    native_manifest, fixture = Path(gate['native_manifest']), Path(gate['fixture'])
    need(not output.exists() and not output.is_symlink() and output.name not in ('actual_terminal.json', 'ACTUAL_HANDOFF.json') and
         not output.resolve().is_relative_to(harness.resolve()) and
         not output.resolve().is_relative_to(root.resolve()) and
         not output.resolve().is_relative_to(native_manifest.parent.parent.resolve()),
         'fresh independent output outside all frozen actual/source/reference trees required')
    plan = gate['plan']
    verify_plan_inputs(plan)
    bind_plan_policy(identity, plan)
    reference_path = Path(config['files']['reference_freeze']['path'])
    reference_pin = dict(plan['inputs'][str(reference_path)], path=str(reference_path))
    reference_raw = pin_read(reference_pin)
    reference_freeze = json.loads(reference_raw)
    source_pins = reference_freeze['comparison_sources']
    need(source_pins[str(root / 'candidates/qwen35_gdn_prefill/full_compare.py')]['sha256'] == FULL_COMPARE_SHA,
         'frozen full_compare source changed')
    def verify_sources():
        for path, record in source_pins.items():
            pin_read(dict(record, path=path))
    verify_sources()
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(root), str(root / 'src'), plan['numpy_site']]
    fc = importlib.import_module('candidates.qwen35_gdn_prefill.full_compare')
    need(Path(fc.__file__).resolve() == root / 'candidates/qwen35_gdn_prefill/full_compare.py',
         'comparison import origin mismatch')
    records = admit_cold_metadata(summary, identity, fc, full_driver_sha256=full_driver_sha, evidence_kind=evidence_kind)
    companion_raw = original['summary']
    companion = json.loads(companion_raw)
    if evidence_kind == 'progress':
        check_companion_summary(companion, summary, identity, fc, full_driver_sha256=full_driver_sha)
    else:
        need(companion_raw == original['summary'], 'summary pin mismatch')
    fc.verify_chunk_exp_seal(identity)
    fc.verify_source_hashes(fc.GATE_SOURCES, root)
    fc.verify_source_hashes(identity['source_sha256'], root)
    for path, expected in identity['identity_file_sha256'].items():
        need(sha(Path(path).read_bytes()) == expected, 'original identity file drift: ' + path)
    values = {}
    for role, record in records.items():
        raw = fc.file_bytes(actual_dir, fc.filename('cold128', role))
        fc.verify_record(raw, record, role)
        values[role] = raw
    from candidates.qwen35_gdn_prefill.input_fixture import load_fixture, gdn
    fixture_manifest, raw_inputs = load_fixture(root, fixture)
    _, weights = gdn.load_payload(root, Path(fixture_manifest['sources']['layer0_directory']))
    inputs = {phase: raw_inputs[phase + '.hidden.bf16le'][:128 * 2048] for phase in fc.PHASES}
    def verify_raw_inputs(current_inputs, current_weights):
        need(identity['authenticated_input_sha256'] == {k: sha(v) for k, v in current_inputs.items()} and
             identity['parameter_sha256'] == {k: sha(v) for k, v in current_weights.items()} and
             identity['input_sha256'] == {k: sha(v) for k, v in inputs.items()},
             'original raw fixture/weights differ from prelaunch identity')
    verify_raw_inputs(raw_inputs, weights)
    native_raw = pin_read(config['files']['native_manifest'])
    need(sha(native_raw) == native_sha, 'official original M128 manifest changed')
    native = json.loads(native_raw)
    fc.validate_manifest(native, native_manifest.parent)
    fc.verify_native_identity(native, root=root)
    need(native['query_tokens'] == 128 and
         native['fixture']['manifest']['sha256'] == sha((fixture / 'manifest.json').read_bytes()) and
         {k: v['sha256'] for k, v in native['payload']['tensors'].items()} == identity['parameter_sha256'],
         'native M128/fixture/weights identity mismatch')
    tensors = fc.NativeTensors(native_manifest.parent, native['tensors'])
    fc.verify_native_continuity(native, tensors, inputs, 128)
    metrics = cold_metrics(fc, values, tensors, weights, root=root, include_conv=include_conv)
    # Pin every source/raw input/actual/native again, not just their JSON reports.
    _recheck_gate(gate, reviewed_code_sha)
    verify_plan_inputs(plan)
    need({k: pin_read(v) for k, v in metadata.items()} == original, 'actual metadata changed during diagnostics')
    need(fc.file_bytes(actual_dir, 'summary.json') == companion_raw, 'original whole-run summary changed during diagnostics')
    need(pin_read(reference_pin) == reference_raw, 'frozen reference inventory changed during diagnostics')
    verify_sources()
    fc.verify_source_hashes(fc.GATE_SOURCES, root)
    fc.verify_source_hashes(identity['source_sha256'], root)
    fc.verify_chunk_exp_seal(identity)
    for path, expected in identity['identity_file_sha256'].items():
        need(sha(Path(path).read_bytes()) == expected, 'original identity file drift after metrics: ' + path)
    for role, record in records.items():
        fc.verify_record(fc.file_bytes(actual_dir, fc.filename('cold128', role)), record, role)
    need(pin_read(config['files']['native_manifest']) == native_raw, 'native manifest changed during diagnostics')
    fc.verify_native_identity(native, root=root)
    for name, record in native['tensors'].items():
        fc.verify_record(fc.file_bytes(native_manifest.parent, record['file']), record, name)
    final_fixture, final_inputs = load_fixture(root, fixture)
    _, final_weights = gdn.load_payload(root, Path(final_fixture['sources']['layer0_directory']))
    need(final_fixture == fixture_manifest, 'fixture manifest changed during diagnostics')
    verify_raw_inputs(final_inputs, final_weights)
    result = dict(schema_version=1, scope='POST_TERMINAL_COLD128_ONLY_DIAGNOSTIC_NOT_FULL_ACCEPTANCE',
        status='COLD_DIAGNOSTIC_COMPLETE', whole_run_status=gate['whole_run_status'],
        recorded_actual_status=summary.get('status'), recorded_launch_status=gate['recorded_launch_status'],
        actual_evidence_kind=evidence_kind, companion_summary_sha256=sha(companion_raw),
        companion_summary_recorded_status=companion.get('status'),
        hash_inventory_origin='genuine_cold_owner_terminal_receipts',
        original_output_files_inventory_present='output_files' in summary,
        original_final_identity_receipt_present='final_identity' in summary,
        original_final_summary_present=companion.get('status') == 'FAILED',
        companion_final_identity_receipt_present='final_identity' in companion,
        companion_final_identity=companion.get('final_identity'),
        passed=None, combined_full_run_acceptance=False, full_block_gate_pass=False,
        cold_gate_scope_only=True, phase='cold128', rows=128, actual_generation=1,
        cold_terminal_count=16, cold_actual_tensor_count=19, all_actual_terminal_count=len(summary['commands']),
        carried_diagnostics_performed=False, carried_result_not_inferred=True,
        terminal_manifest_sha256=gate['terminal_manifest_sha256'], plan_sha256=plan_sha,
        reviewed_configuration_sha256=reviewed_config_sha, reviewed_code_pins_sha256=reviewed_code_sha,
        source_commit=source_commit, actual_evidence_sha256=sha(original[evidence_kind]),
        actual_identity_sha256=sha(original['identity']), native_manifest_sha256=native_sha,
        actual_directory=str(actual_dir), native_manifest=str(native_manifest),
        cold_receipt_tensor_inventory={fc.filename('cold128', k): v for k, v in records.items()},
        actual_source_sha256=identity['source_sha256'], actual_identity_file_sha256=identity['identity_file_sha256'],
        raw_input_sha256=identity['input_sha256'], parameter_sha256=identity['parameter_sha256'],
        original_final_identity=summary.get('final_identity'), comparison_source_pins=source_pins,
        frozen_gate_source_sha256=fc.GATE_SOURCES, numerical_thresholds_changed=False,
        bf16_comparison_domain=fc.BF16_COMPARISON_DOMAIN, prep_threshold_assigned=False,
        original_native_cache_continuity_verified=True, actual_cold_root_carried_binding_verified=True,
        before_after_pins_verified=True, frozen_plan_inputs_before_after_verified=True,
        frozen_plan_input_count=len(plan['inputs']),
        actual_numerical_policy={right: identity[right] for _, right in POLICY_PAIRS},
        conv_reference_arithmetic_selected=include_conv,
        actual_rerun=False, official_block_recaptured=False, downstream_golden_injection=False,
        actual_terminal_fabricated=False, actual_handoff_fabricated=False,
        hardware_executed=False, rtl_executed=False, hardware_cycles=None, metrics=metrics)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--reviewed-config-sha256', required=True)
    parser.add_argument('--reviewed-code-pins-sha256', required=True)
    parser.add_argument('--terminal-manifest', required=True)
    parser.add_argument('--reviewed-terminal-sha256', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--include-conv', action='store_true', help='Requires explicit permission in reviewed terminal handoff.')
    args = parser.parse_args(argv)
    result = run_diagnostic(args.terminal_manifest, args.reviewed_terminal_sha256,
                            args.output, config_path=args.config, reviewed_config_sha=args.reviewed_config_sha256,
                            reviewed_code_sha=args.reviewed_code_pins_sha256, include_conv=args.include_conv)
    print(json.dumps({k: result[k] for k in ('status', 'whole_run_status', 'passed', 'combined_full_run_acceptance')}))
    # 0 means the diagnostic completed, NEVER numerical/full-run acceptance.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
