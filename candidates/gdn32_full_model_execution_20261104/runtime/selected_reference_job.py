"""Stricter selected-policy envelope around the byte-unchanged reference job.
Only the original pinned producer is run. The complete emitted tensor/state
schema, metadata, source closure and strict outer ownership are verified. This
is software-reference/data evidence, never runtime liveness or numerical PASS.
"""
import importlib.util
import json
import math
import pathlib

P = pathlib.Path
D = P(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


a = load('selected_reference_acquisition', D / 'selected_acquisition.py')
need, sha, pin, same = a.need, a.sha, a.pin, a.same
ORIGINAL_JOB_SHA = 'aa0a9e02ce983029cda391b8a21e517f04e2c567cad49809f163ae12a211df01'
ORIGINAL_PHASE_SHA = '8eec3a41a45ef4319335c20330a4832b8cb4a401be37e09909f5e2f7970971a5'
SOURCE_SHAS = ('5e4f13f2117e675ca9e308bf01cb7003003df21d9b9d8c59776cef0e1b69e9e4',
               'd4f779881ebea182c747064fa159da7379fc45802232f04d04c013fe3d0aabd2')
KEYS = ('qwen2', 'qwen35_08b', 'qwen35_08b', 'qwen35_35b', 'qwen35_35b')
SIDECAR_SHAS = {'qwen2': '17d159b19e98d6f104bbaba1bd62ea2de96b5bcde8185230135c6a96d445628f',
                 'qwen35_08b': '8a6ba34b3e85bac5427d25a44e97659f6eeaa341392e1bc6d35906434422aada',
                 'qwen35_35b': '79078825f230ffecf33fff9b838d40b155217b025accf26e961927a25a475743'}
SCOPE = 'SELECTED_ORIGINAL_REFERENCE_DATA_ONLY_NOT_RUNTIME_OR_DUT_PASS'


def producer(b, i):
    relative = 'candidates/' + ('independent_reference_p0_cache_arm_20261028T2313' if i == 0 else
                               'independent_block_reference_prepare_v3_20261028T2312')
    path = a.checked_source(b, relative + '/run_reference.py')
    need(sha(path) == SOURCE_SHAS[0 if i == 0 else 1], 'unchanged exact original reference producer')
    for name in ('profiles.json', 'tensor_acquisition_plan.json', 'stimulus.py'):
        a.checked_source(b, relative + '/' + name)
    if i:
        a.checked_source(b, relative + '/router_local_observer.py')
    need(sha(path.parent / 'profiles.json') == a.PROFILE_SHA, 'exact original reference profile source')
    need(sha(path.parent / 'tensor_acquisition_plan.json') == 'df2d2a42cb3fa7c837b78ff5aabceca147f64015f1c3f36393deac76d826609f',
         'unchanged original reference weight geometry')
    return path


def tensor_schema(profile, config):
    """Original fixed M128 schema, derived from the pinned official config."""
    i = profile['profile']
    c = config if i == 0 else config['text_config']
    width, heads, kv = c['hidden_size'], c['num_attention_heads'], c['num_key_value_heads']
    head = c.get('head_dim', width // heads)
    out = {}
    calls = {}

    def add(name, shape, dtype='torch.bfloat16', folder='reference_only'):
        out[name] = dict(file=folder + '/' + name + '.bin', shape=shape, dtype=dtype,
                         bytes=math.prod(shape) * {'torch.bfloat16': 2, 'torch.float32': 4, 'torch.int64': 8}[dtype])

    def stage(name, shape, suffix=''):
        calls[name] = 1
        add('stage.' + name + '.0' + suffix, shape)

    for name in ('hidden_native', 'hidden_storage'):
        add(name, [1, 128, width], 'torch.float32' if name == 'hidden_storage' and i == 0 else 'torch.bfloat16', 'input_only')
    add('positions', [1, 128], 'torch.int64', 'input_only')
    for name in ('rope_cos', 'rope_sin'):
        add(name, [128, head] if i == 0 else [1, 128, 64], 'torch.float32' if i == 0 else 'torch.bfloat16', 'input_only')
    if i == 0:
        add('causal_mask', [1, 1, 128, 128], folder='input_only')
    else:
        add('rope_packed', [1, 128, 64], folder='input_only')
    add('baseline_output', [1, 128, width])
    add('output_storage', [1, 128, width], 'torch.float32' if i == 0 else 'torch.bfloat16')
    stage('input_layernorm', [1, 128, width])
    stage('post_attention_layernorm', [1, 128, width])
    if i in (1, 3):
        conv = 2 * c['linear_num_key_heads'] * c['linear_key_head_dim'] + c['linear_num_value_heads'] * c['linear_value_head_dim']
        states = {'conv_states.0': ([1, conv, c['linear_conv_kernel_dim']], 'torch.bfloat16'),
                  'recurrent_states.0': ([1, c['linear_num_value_heads'], c['linear_key_head_dim'], c['linear_value_head_dim']], 'torch.float32')}
        stage('linear_attn', [1, 128, width])
    else:
        states = {name: ([1, kv, 128, head], 'torch.bfloat16') for name in ('keys', 'values')}
        stage('self_attn.q_proj', [1, 128, heads * head * (1 if i == 0 else 2)])
        for name in ('k_proj', 'v_proj'):
            stage('self_attn.' + name, [1, 128, kv * head])
        if i:
            stage('self_attn.q_norm', [1, 128, heads, head])
            stage('self_attn.k_norm', [1, 128, kv, head])
        stage('self_attn.o_proj', [1, 128, width])
        stage('self_attn', [1, 128, width], '.0')
        stage('self_attn', [1, heads, 128, 128], '.1')
    for state, (shape, dtype) in states.items():
        for arm in ('baseline_cache.', 'final_cache.'):
            add(arm + state, shape, dtype)
    if i in (3, 4):
        for name in ('gate_proj', 'up_proj'):
            stage('mlp.shared_expert.' + name, [128, c['shared_expert_intermediate_size']])
        stage('mlp.shared_expert.down_proj', [128, width])
        stage('mlp.gate', [128, c['num_experts']], '.0')
        stage('mlp.gate', [128, c['num_experts_per_tok']], '.1')
        add('stage.mlp.gate.0.2', [128, c['num_experts_per_tok']], 'torch.int64')
        add('stage.mlp.gate.0.pre_topk_probs', [128, c['num_experts']], 'torch.float32')
    else:
        for name in ('gate_proj', 'up_proj'):
            stage('mlp.' + name, [1, 128, c['intermediate_size']])
        stage('mlp.down_proj', [1, 128, width])
    stage('mlp', [1, 128, width])
    return out, calls


def checked_pin(row, cap=2 << 20):
    need(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'} and type(row['bytes']) is int
         and 0 < row['bytes'] <= cap, 'exact bounded selected reference pin')
    path = P(row['path'])
    need(path.is_absolute() and path == path.resolve() and path.is_file()
         and all(not item.is_symlink() for item in (path, *path.parents)), 'canonical selected reference input')
    need(same(pin(path), row), 'selected reference actual bytes')
    return path


def verify_result(b, i, result_pin, runtime):
    policy = a.policy(b)
    policy.require_profile(b, i)
    source = producer(b, i)
    profile = a.profiles(b)[i]
    config = a.checked_source(b, 'config/upstream/weight_headers/' + profile['model'] + '/config.json')
    need(sha(config) == profile['config_sha256'], 'original reference config')
    path = checked_pin(result_pin)
    doc = json.loads(path.read_text())
    need(same(doc['profile'], profile), 'exact original profile seed/config/CPU/framework/source/geometry')
    need(doc['status'] == 'CAPTURED_FRESH_OFFICIAL_FULL_BLOCK_REFERENCE_ONLY'
         and type(doc['complete_block_tokens']) is int and doc['complete_block_tokens'] == 128
         and type(doc['forward_calls']) is int and doc['forward_calls'] == 2
         and doc['exact_baseline_observer_output_equal'] is True and doc['hardware_executed'] is False
         and doc['numerical_comparison_with_hardware'] is False
         and doc['no_reference_outputs_or_router_ids_allowed_in_hardware_stimulus'] is True
         and doc['input_identity'] == 'NEW_EXTERNAL_BOUNDARY_NOT_HISTORICAL_PREFIX'
         and doc['router_policy'] == 'UNMODIFIED_OFFICIAL_TORCH_TOPK', 'original complete cold-state software reference only')
    for key in ('receipt', 'sidecar'):
        checked_pin(runtime[key])
    need(runtime['sidecar']['sha256'] == SIDECAR_SHAS[KEYS[i]], 'original independently derived framework sidecar')
    sidecar = json.loads(P(runtime['sidecar']['path']).read_text())
    need(sidecar['framework_revision'] == profile['framework_revision']
         and sidecar['module_sha256'].get('transformers.models.' + profile['module'] + '.modeling_' + profile['module']) == profile['source_sha256'],
         'original framework/model source identity')
    need(doc['runtime_receipt_sha256'] == runtime['receipt']['sha256']
         and doc['runtime_source_pins_sha256'] == runtime['sidecar']['sha256'], 'exact original runtime provenance, no liveness transfer')
    schema, calls = tensor_schema(profile, json.loads(config.read_text()))
    need(type(doc['tensor_records']) is dict and set(doc['tensor_records']) == set(schema)
         and same(doc['observed_module_calls'], calls), 'complete original tensor/state/module inventory')
    if i:
        need(doc['raw_router_score_observation'] == ('ORIGINAL_FORWARD_LOCAL_RETURN_READONLY_PROFILE' if i in (3, 4) else 'NOT_APPLICABLE'),
             'original same-forward raw router score observation')
    files = set()
    for name, expected in schema.items():
        row = doc['tensor_records'][name]
        need(type(row) is dict and set(row) == set(expected) | {'sha256'}
             and all(same(row[field], value) for field, value in expected.items()), 'exact original reference tensor shape/type/path/bytes')
        tensor = checked_pin(dict(path=str(path.parent / row['file']), bytes=row['bytes'], sha256=row['sha256']), 128 << 20)
        files.add(tensor)
    need(files == set(path.parent.rglob('*.bin')), 'complete original reference tensor file inventory')
    for name in schema:
        if name.startswith('baseline_cache.'):
            final = 'final_cache.' + name.removeprefix('baseline_cache.')
            need(doc['tensor_records'][name]['sha256'] == doc['tensor_records'][final]['sha256'], 'unaltered complete final cache state')
    if i:
        need(doc['tensor_records']['baseline_output']['sha256'] == doc['tensor_records']['output_storage']['sha256'], 'unaltered observed full output')
    checked_pin(result_pin)
    return doc


def strict(record, argv):
    need(record.get('status') == 'PASS_PROCESS_ONLY' and type(record.get('native_exit')) is int
         and record['native_exit'] == 0 and record.get('errors') == [] and record.get('argv') == list(map(str, argv)),
         'original exact reference invocation native success')
    need((record.get('cleanup_proof') or {}).get('status') == 'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'
         and (record.get('log_capture') or {}).get('pipe_eof_observed') is True
         and (record.get('log_capture') or {}).get('gzip_finalized') is True,
         'reference strict complete ownership cleanup and log EOF')


def run(b, stage):
    p = a.policy(b)
    for name in ('selected_acquisition.py', 'selected_reference_job.py', 'reference_job.py', 'reference_phase.py'):
        a.checked_source(b, 'candidates/gdn32_full_model_execution_20261104/runtime/' + name)
    need(sha(D / 'reference_job.py') == ORIGINAL_JOB_SHA and sha(D / 'reference_phase.py') == ORIGINAL_PHASE_SHA,
         'byte-unchanged original reference job and outer phase')
    selected = p.eligible(b)
    for i in selected:
        producer(b, i)
    audited = {}

    def owned_stage(name, argv, seconds, rss, extra_pins, **kwargs):
        need(name.startswith('reference') and name[9:].isdigit(), 'only exact selected reference stages')
        i = int(name[9:])
        need(i in selected and str(i) not in audited, 'one original stage for each selected profile')
        record = stage(name, argv, seconds, rss, extra_pins, **kwargs)
        # Preserve the original runner's hold-lease-on-incomplete-cleanup behavior.
        original = load('selected_original_reference_ownership', D / 'reference_job.py')
        if not original.complete(record):
            return record
        strict(record, argv)
        home = P(b['output']) / ('profile' + str(i))
        phase_pin = pin(home / 'PHASE.json')
        phase = json.loads((home / 'PHASE.json').read_text())
        args = phase['argv']
        src = producer(b, i)
        profile = a.profiles(b)[i]
        config = P(b['repo']) / 'config/upstream/weight_headers' / profile['model'] / 'config.json'
        receipt = pin(args[args.index('--runtime-receipt') + 1])
        sidecar = pin(args[args.index('--runtime-source-pins') + 1])
        dest = home / 'actual/reference'
        expected = [str(src), '--profile', str(i), '--payload', b['payload'], '--config', str(config),
                    '--runtime-receipt', receipt['path'], '--runtime-receipt-sha256', receipt['sha256'],
                    '--runtime-source-pins', sidecar['path'], '--runtime-source-pins-sha256', sidecar['sha256'],
                    '--output', str(dest), '--execute-reviewed']
        need(same(phase, dict(argv=expected, source_sha256=sha(src))), 'exact original reference phase binding')
        need(list(map(str, argv))[1:] == [str(D / 'reference_phase.py'), '--binding', str(home / 'PHASE.json'), '--sha256', phase_pin['sha256']],
             'exact original reference outer phase invocation')
        outer_pin = pin(home / 'actual/RESULT.json')
        strict(json.loads(checked_pin(outer_pin).read_text()), argv)
        result_pin = pin(dest / 'RESULT.json')
        verify_result(b, i, result_pin, dict(receipt=receipt, sidecar=sidecar))
        audited[str(i)] = dict(result=result_pin, phase=phase_pin, outer=outer_pin)
        return record

    refs = load('selected_original_reference_job', D / 'reference_job.py').run(b, owned_stage)
    need(set(refs) == set(audited) == set(map(str, selected)), 'all and only selected complete references')
    index_pin = pin(P(b['output']) / 'REFERENCES.json')
    index = json.loads(checked_pin(index_pin).read_text())
    need(same(index, dict(execution_policy=p.checked(b), scope='REGISTERED_FIVE_ELIGIBLE_SOFTWARE_REFERENCES_NOT_DUT',
                         references=refs, identity=b['identity'])), 'exact original complete selected reference manifest')
    need({item.name for item in P(b['output']).glob('profile*')} == {'profile' + str(i) for i in selected}, 'no unselected reference output')
    with (P(b['output']) / 'SELECTED_REFERENCE_VALIDATION.json').open('x') as handle:
        json.dump(dict(schema='SELECTED_ORIGINAL_REFERENCE_VALIDATION_V1', scope=SCOPE,
                       execution_policy=p.checked(b), identity=b['identity'], references_manifest=index_pin,
                       references=audited, numerical_pass=False, runtime_pass=False), handle, indent=2)
    return refs
