"""Exact-origin, read-only admission proposal for existing paired M16 references.

No imports of the DUT/native framework, tensor decoding, subprocesses or writes.
The metadata-only default never opens payloads, exports or ELF files. Neither
mode is numerical admission: the new packed source/observer profile is separate.
"""
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat

HERE = Path(__file__).resolve().parent
PINS_SHA256 = 'af964fe867b35780fcfb48428c300a1504ec9b098c9fb350e5628033d9c05c8d'
PROFILE = 'qwen2-public-pv16-packed-m16-reuse-proposal-v1'
MAX_JSON = 2 * 1024 * 1024
MODES = ('bf16', 'fp32')
METHODS = ('official_self_cache', 'independent_self_cache')
STAGES = (('n0',1536),('qr',1536),('kr',256),('v',256),('q',1536),
          ('k',256),('att',1536),('o',1536),('r',1536),('n1',1536),
          ('gate',8960),('up',8960),('act',8960),('down',1536),('y',1536))


def need(value, message):
    if not value:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    need(isinstance(raw, bytes) and len(raw) <= MAX_JSON, 'JSON byte bound')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('nonfinite JSON value')
    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    # The decoder can overflow a finite-looking exponent to infinity.
    encoded(result)
    return result


def digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def same(left, right):
    return encoded(left) == encoded(right)


def safe_path(path, *, directory=False):
    path = Path(path).absolute()
    need('..' not in path.parts, 'path traversal')
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        need(not stat.S_ISLNK(current.lstat().st_mode), 'symlink path')
    mode = path.lstat().st_mode
    need(stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode), 'path type')
    return path.resolve(strict=True)


def below(root, relative):
    need(type(relative) is str and relative and '\\' not in relative and '\x00' not in relative,
         'artifact name')
    p = PurePosixPath(relative)
    need(not p.is_absolute() and all(x not in ('', '.', '..') for x in relative.split('/')),
         'relative normalized artifact required')
    root = safe_path(root, directory=True)
    result = safe_path(root / relative)
    need(result.is_relative_to(root), 'artifact outside root')
    return result


def file_hash(path):
    value = hashlib.sha256()
    with safe_path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            value.update(block)
    return value.hexdigest()


def checked(root, item, *, content):
    need(type(item) is dict and set(item) == {'path','bytes','sha256'}, 'file record schema')
    need(type(item['bytes']) is int and 0 <= item['bytes'] <= 256 * 1024 * 1024
         and digest(item['sha256']), 'file record types')
    path = below(root, item['path'])
    need(path.stat().st_size == item['bytes'], 'file byte count changed')
    if content:
        need(file_hash(path) == item['sha256'], 'file content changed')
    return path


def read_metadata(root, relative, pin):
    path = below(root, relative)
    need(type(pin['bytes']) is int and 0 <= pin['bytes'] <= MAX_JSON
         and path.stat().st_size == pin['bytes'], 'metadata size')
    with path.open('rb') as stream:
        raw = stream.read(MAX_JSON + 1)
    need(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'], 'metadata digest changed')
    return strict_json(raw)


def contract():
    raw = safe_path(HERE / 'pins.json').read_bytes()
    need(sha(raw) == PINS_SHA256, 'reviewed reuse contract changed')
    result = strict_json(raw)
    need(result['profile'] == PROFILE and result['status'] == 'PREPARATION_ONLY_PENDING_REVIEW'
         and result['execution']['allowed_by_this_contract'] is False, 'proposal-only contract')
    return result


def snapshot():
    """Proposal source closure for the future linked launch contract to freeze."""
    return {name:file_hash(HERE/name) for name in
            ('reuse.py','producer.py','pins.json','test_assets.py','README.md')}


def shapes():
    result = {name:[1,16,1536] for name in ('x','n0','qr','att','o','r','n1','down','y')}
    result.update({name:[1,16,256] for name in ('kr','v')})
    result.update({name:[1,16,8960] for name in ('gate','up','silu','act')})
    result.update({name:[1,12,16,16] for name in ('scores','logits','prob','softmax_fp32')})
    result.update({name:[1,2,16,128] for name in ('cache_k','cache_v','k')})
    result.update({name:[1,12,16,128] for name in ('repeat_k','repeat_v','q','pv')})
    result.update(mask=[1,1,16,16], cos=[16,128], sin=[16,128])
    return result


def export_shapes():
    result = shapes()
    result.update(q=[1,16,1536], k=[1,16,256])
    return result


def output_inventory():
    result = {'phase_%d_%s_recipe.f32le'%(i,name):16*width*4
              for i,(name,width) in enumerate(STAGES)}
    result.update({name+'.f32le':4*math.prod(shape) for name,shape in shapes().items()
                   if name in ('cache_k','cache_v','scores','logits','softmax_fp32','prob','silu')})
    return result


def validate_native(value, declared, payload_sha):
    """Recheck original logical/export shapes and verdict metadata, without arrays."""
    need(value['status'] == 'PASS_BF16_STAGE_BUDGET' and type(value['tokens']) is int
         and value['tokens'] == 16 and value['carried'] is False
         and value['m16_gate_sha256'] is None and type(value['torch_threads']) is int
         and value['torch_threads'] == 4 and value['payload_manifest_sha256'] == payload_sha,
         'native M16 scope')
    for name in ('rtl_execution','hardware_recipe_acceptance','logits','full_model_quality',
                 'manifest_whole_checkpoint_hash_verified'):
        need(value[name] is False, 'native acceptance claim drift')
    need(value['official_framework_forward'] is True and set(value['modes']) == set(MODES),
         'native reference modes')
    need(same(value['policy']['operator'],{'max_abs':0.03125,'mean_abs':0.005}) and
         same(value['policy']['block'],{'max_abs':0.05,'mean_abs':0.01}) and
         value['policy']['sha256'] == '5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5',
         'unchanged original numerical policy')
    need(declared['producer'] == 'qwen2-native-qkv-qk-pair-generated-v1', 'recipe-native producer')
    shape_map, export_map = shapes(), export_shapes()
    need(set(declared['outputs']) == set(MODES), 'native export precision inventory')
    for mode in MODES:
        phases = value['modes'][mode]['phases']
        need(type(phases) is list and len(phases) == 1, 'native cold phase count')
        phase = phases[0]
        need(type(phase['phase']) is int and phase['phase'] == 0 and
             type(phase['past_tokens']) is int and phase['past_tokens'] == 0 and
             phase['token_ids'] == phase['position_ids'] == list(range(16)) and
             all(type(v) is int for v in phase['token_ids'] + phase['position_ids']), 'native token positions')
        expected_semantics = {'mask_exact','native_fp32_probability_sum_within_2e_5',
            'independent_fp32_probability_sum_within_2e_5','native_cache_append_k_exact',
            'native_cache_append_v_exact','independent_cache_append_k_exact',
            'independent_cache_append_v_exact','native_future_probability_zero','independent_future_probability_zero'}
        need(set(phase['semantics']) == expected_semantics and
             all(v is True for v in phase['semantics'].values()) and phase['all_semantics_exact'] is True,
             'native semantic checks')
        need(set(phase['stages']) == set(shape_map) and set(declared['outputs'][mode]) == set(METHODS),
             'native stage/method inventory')
        failures = []
        for method in METHODS:
            need(set(declared['outputs'][mode][method]) == set(shape_map), 'native export stage inventory')
        for name, shape in shape_map.items():
            item = phase['stages'][name]
            need(same(item['shape'],shape) and type(item['elements']) is int and
                 item['elements'] == math.prod(shape) and item['finite'] is True, 'native stage geometry/finite')
            if name == 'mask':
                need(item['contract'] == 'exact_causal_mask' and item['bit_exact'] is True and
                     item['passed'] is True, 'exact native causal mask')
            elif mode == 'fp32' or name == 'softmax_fp32':
                need(item['passed'] is None and item['contract'] is None and
                     item['status'] == 'DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE', 'diagnostic-only FP32')
            else:
                limits = value['policy']['block' if name == 'y' else 'operator']
                need(same(item['limits'],limits) and all(type(item[k]) in (int,float) and
                     math.isfinite(item[k]) and 0 <= item[k] <= limits[k] for k in ('max_abs','mean_abs'))
                     and item['passed'] is True and item['contract'] == 'spec/numerical_contract.md:'+
                     ('block' if name == 'y' else 'operator'), 'unchanged native BF16 stage limits')
            if item['passed'] is False:
                failures.append(name)
            for method, prefix in zip(METHODS, ('native','independent')):
                record = declared['outputs'][mode][method][name]
                relative = '%s/phase_0/%s_%s.f32le' % (mode,prefix,name)
                need(item[prefix+'_file'] == relative and same(item[prefix+'_export_shape'],export_map[name])
                     and record['path'] == 'native_m16/' + relative and type(record['bytes']) is int
                     and record['bytes'] == 4*math.prod(shape)
                     and item[prefix+'_file_sha256'] == record['sha256'], 'native export shape/path/hash')
        need(phase['failed_stages'] == failures, 'native failure inventory')
        need(phase['status'] == ('PASS_BF16_STAGE_BUDGET' if mode == 'bf16' else 'DIAGNOSTIC_FP32'),
             'native phase status')


def records(value):
    if type(value) is dict:
        if set(value) == {'path','bytes','sha256'}:
            yield value
        else:
            for item in value.values():
                yield from records(item)
    elif type(value) is list:
        for item in value:
            yield from records(item)


def reuse_records(assets):
    """Intentionally excludes every M128 activation/reference/arena."""
    selected = [assets['payload'], assets['native_m16'], assets['library'], assets['recipe'],
                {'table':assets['readonly']['table']}]
    for role in ('sequential','reduced'):
        selected.append({key:assets[role][key] for key in ('cpp','header','executable','compile')})
    return [item for value in selected for item in records(value)]


def no_aliases(paths):
    seen_paths, seen_inodes = set(), set()
    for path in paths:
        path = safe_path(path)
        st = path.stat(); inode = (st.st_dev,st.st_ino)
        need(path not in seen_paths and inode not in seen_inodes, 'cross-artifact path/inode alias')
        seen_paths.add(path); seen_inodes.add(inode)


def verify_reuse(origin_root, *, metadata_only=True):
    """Opaque hashing is opt-in and is not invoked by the plan-only CLI/tests."""
    need(type(metadata_only) is bool, 'canonical metadata-only mode')
    pins = contract(); root = safe_path(origin_root, directory=True)
    meta = {name:read_metadata(root,name,pin) for name,pin in pins['metadata'].items()}
    assets = meta['private/assets/ASSETS.json']; setup = meta['private/assets/SETUP.json']
    summary = meta['private/setup_evidence/summary.json']; backend = meta['private/assets/backend.json']
    need(assets['profile'] == pins['origin_asset_profile'] and assets['status'] == 'READY_FOR_ACTUAL_M128'
         and type(assets['rows']) is int and assets['rows'] == 128 and assets['past_tokens'] == 0,
         'origin remains M128; relabeling is forbidden')
    need(setup['status'] == summary['status'] == 'COMPLETE_FRESH_SETUP' and
         setup['rows'] == 128 and setup['past_tokens'] == 0 and setup['enable_raw_kv'] is True
         and setup['checkout_commit'] == pins['origin_commit']
         and setup['source_recheck'] == summary['source_recheck'] == 'UNCHANGED'
         and setup['completed_phases'] == summary['completed_phases']
         and setup['asset_manifest_sha256'] == summary['manifest_sha256'] == pins['metadata']['private/assets/ASSETS.json']['sha256']
         and summary['setup_receipt_sha256'] == pins['metadata']['private/assets/SETUP.json']['sha256'],
         'origin setup/asset linked receipts')
    workspace = safe_path(root/'private/assets', directory=True); st=workspace.stat()
    need(setup['workspace'] == {'path':str(workspace),'device':st.st_dev,'inode':st.st_ino},
         'origin workspace identity')
    for item in (assets,setup,summary):
        need(item['source_manifest_sha256'] == pins['source_manifest_sha256'], 'origin source manifest')
    need(sha(encoded(assets['source_sha256'])) == pins['source_manifest_sha256']
         and setup['source_sha256'] == assets['source_sha256'], 'origin source map binding')
    for relative, expected in assets['source_sha256'].items():
        need(file_hash(below(root/'private/checkout', relative)) == expected, 'origin source changed: '+relative)
    need(backend['cpu_capability'] == 'AVX512' and backend['torch_commit'] ==
         '449b1768410104d3ed79d3bcfe4ba1d65c7f22c0' and backend['intraop_threads'] == 4
         and backend['interop_threads'] == 1 and backend['deterministic'] is True, 'recorded backend policy')
    native = meta['private/assets/native_m16/RESULT.json']
    validate_native(native,assets['native_m16'],assets['payload']['manifest']['sha256'])
    identity = dict(native['identity']); identity.pop('independent_qkv_recipe')
    identity['runner_sha256'] = backend['identity']['runner_sha256']
    need(identity == backend['identity'], 'recorded native/backend identity binding')
    need(native['identity']['runner_sha256'] == assets['recipe']['generated_module']['sha256']
         and native['identity']['independent_qkv_recipe']['backend_order_proven'] is False,
         'explicit generated recipe identity')
    declared = reuse_records(assets)
    paths=[]
    for item in declared:
        suffix=PurePosixPath(item['path']).suffix
        content = not metadata_only or suffix in ('.json','.py','.cpp','.h')
        paths.append(checked(workspace,item,content=content))
    no_aliases(paths)
    if not metadata_only:
        for name in ('private/assets/library/official_bf16_compile.json',
                     'private/assets/sequential/compile.json','private/assets/reduced/compile.json'):
            compiler=meta[name]['compiler']
            need(file_hash(compiler['path']) == compiler['sha256'],'origin compiler bytes changed')
    # These exact historical receipts remain unchanged; no fresh claim is made.
    return dict(schema=1,profile=PROFILE,status=('METADATA_ONLY_NOT_READY' if metadata_only else
        'OPAQUE_ORIGIN_BYTES_VERIFIED_NOT_READY'),origin=str(root),origin_commit=pins['origin_commit'],
        contract_sha256=PINS_SHA256,origin_manifest_sha256=pins['metadata']['private/assets/ASSETS.json']['sha256'],
        native_m16_result_sha256=assets['native_m16']['result']['sha256'],
        source_manifest_sha256=pins['source_manifest_sha256'],source_files=len(assets['source_sha256']),
        artifact_records=len(declared),payload_bytes_hashed=not metadata_only,
        current_backend_verified=False,packed_source_profile_linked=False,
        ready_for_actual=False,**pins['claims'])
