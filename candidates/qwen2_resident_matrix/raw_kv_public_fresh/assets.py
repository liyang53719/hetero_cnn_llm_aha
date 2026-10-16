"""Explicit fresh M16 asset provenance; no archived receipt identities are rewritten.

Preflight streams hashes only. Numerical reference arrays are decoded solely by
post-terminal comparison helpers, under the existing whole-reference gate.
This module never downloads, builds, executes a producer or loads a native ELF.
"""
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PROFILE = 'qwen2-public-pv16-fresh-assets-v1'
STATUS = 'READY_FOR_ACTUAL_M16'
MODEL = 'Qwen/Qwen2-1.5B-Instruct'
REVISION = 'ba1cf1846d7df0a0591d6c00649f57e798519da8'
LEDGER = 'config/payload_pins/qwen2_layer0.json'
LEDGER_SHA256 = '190e1fca0edff7c783c6981a6759f57162e63c4754ffc0f3481df64de9d06f88'
ARENA_BYTES = 188043264
ARENA_SHA256 = '0a94ea142c28a6c1ce4b8ad928caecee9c5721bb6e4bc0eb097eebd8202aabf8'
INPUT_X_SHA256 = '271b8498d6c764d48a7f63fb3f314a49b3bafb7b8f62e15bf70fb2595777349c'
M128_X_SHA256 = 'ddcdcca67cb3e26007880a78074ea3eb70bf83e8d8060fa2258bb2c7644695df'
TABLE_SHA256 = '5edc3314874c1cf4a7dc9cb54f2c824b18272048f70abcf9021f021308589045'
HEADER_SHA256 = '79d4b81277f3431d2e89e6807dc2deee425957a5549c7fffa71d8db8cba9af30'
CPP_SHA256 = {
    'sequential': '0cdfd2c6927eec8dfb72e315e9a1107d6966d47b6326de077bf77a9e3a73ded6',
    'reduced': 'e13bddc69714e6af6a774198d7382b4100f2f50cd843eea5d780bace14c6aacf',
}
PRODUCERS = {'sequential': 'original-rms-rope-sequential-v2',
             'reduced': 'original-rms-rope-qkv-block-pair-v1'}
NATIVE_PRODUCER = 'scripts.qwen2_layer0_model_gate.run_gate'
METHODS = ('official_self_cache', 'independent_self_cache')
MODES = ('bf16', 'fp32')
MAX_MANIFEST_BYTES = 262144
MAX_METADATA_BYTES = 2097152
MAX_STDOUT_BYTES = 16384
OWN_INPUTS = ('assets.py','official_entry.patch','public_entry.patch','prepare.py','pins.json','README.md','test_assets.py')
IMPORTED_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
STAGES = (('n0',1536),('qr',1536),('kr',256),('v',256),('q',1536),('k',256),
          ('att',1536),('o',1536),('r',1536),('n1',1536),('gate',8960),('up',8960),
          ('act',8960),('down',1536),('y',1536))
TENSOR_PINS = {'embed_tokens.rows_0_255': {'bytes': 786432,
                             'sha256': '3cdd8eecf1d0948c6ebf40ca947875b7b706521733fa3107e934d3815e45c014',
                             'shape': [256, 1536]},
 'input_layernorm.weight': {'bytes': 3072,
                            'sha256': 'ea77d5968e396420086f0c6c45c08df4ca4228e0c8a0be5d6ec5d0d247110a0e',
                            'shape': [1536]},
 'mlp.down_proj.weight': {'bytes': 27525120,
                          'sha256': '8a9657234cffb29cec816483e03454846d80d3a1f4171e6bc40479f3ba73ce5a',
                          'shape': [1536, 8960]},
 'mlp.gate_proj.weight': {'bytes': 27525120,
                          'sha256': '0219acbf1f5bc38fc55ee56fa6b55c82150a1a4279915090e857beb382cc0d7e',
                          'shape': [8960, 1536]},
 'mlp.up_proj.weight': {'bytes': 27525120,
                        'sha256': 'a403942b0dc208a543e8434d091564cfd4b7a091c291d02d7a62ae46884e61ed',
                        'shape': [8960, 1536]},
 'post_attention_layernorm.weight': {'bytes': 3072,
                                     'sha256': '762cfb39d378a8f4f1d2cdf1781a94089613e51d395acc0f4d3578be2459400a',
                                     'shape': [1536]},
 'self_attn.k_proj.bias': {'bytes': 512,
                           'sha256': '56a716f9fd535d659a918afc9b7d25ad1d159dc0e9bd6da68549a155bb62ada0',
                           'shape': [256]},
 'self_attn.k_proj.weight': {'bytes': 786432,
                             'sha256': 'addac2eb287cc8d8caa24178c94156c67bab35bc6a9f76927f50a4f0be0ade47',
                             'shape': [256, 1536]},
 'self_attn.o_proj.weight': {'bytes': 4718592,
                             'sha256': '7613bde8e47278a40bbf05222cd0799ed873194e56a96f2f6167d4580bb1a735',
                             'shape': [1536, 1536]},
 'self_attn.q_proj.bias': {'bytes': 3072,
                           'sha256': 'c68e4379e1c3701dabe73e98cda2fc87c85cce47adb6e4dc7f871fba9f497d9d',
                           'shape': [1536]},
 'self_attn.q_proj.weight': {'bytes': 4718592,
                             'sha256': '142ece1271ee9eb6b1e91055e2a6293a5572bf9b5395c56c77f9584728ee89d4',
                             'shape': [1536, 1536]},
 'self_attn.v_proj.bias': {'bytes': 512,
                           'sha256': '4ed960cd1895ac1bcc5012a0948f9b73e50b411b9b8015e9941d28e8d45fd29d',
                           'shape': [256]},
 'self_attn.v_proj.weight': {'bytes': 786432,
                             'sha256': 'e99b01559f13e11a0c96309f5b4e11664223aa31a2f318e49597ad8e66b0ea32',
                             'shape': [256, 1536]}}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def exact(value, keys, message):
    need(type(value) is dict and set(value) == set(keys), message)


def digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def same(actual, expected):
    """Canonical JSON equality, including integer versus boolean dimensions."""
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return set(actual) == set(expected) and all(same(actual[k],v) for k,v in expected.items())
    if type(expected) is list:
        return len(actual) == len(expected) and all(same(a,b) for a,b in zip(actual,expected))
    return actual == expected


def shapes():
    result = {name:[1,16,1536] for name in ('x','n0','qr','att','o','r','n1','down','y')}
    result.update({name:[1,16,256] for name in ('kr','v')})
    result.update({name:[1,16,8960] for name in ('gate','up','silu','act')})
    result.update({name:[1,12,16,16] for name in ('scores','logits','prob','softmax_fp32')})
    result.update({name:[1,2,16,128] for name in ('cache_k','cache_v')})
    result.update({name:[1,12,16,128] for name in ('repeat_k','repeat_v','q','pv')})
    result.update(k=[1,2,16,128], mask=[1,1,16,16], cos=[16,128], sin=[16,128])
    return result


def export_shapes():
    result = shapes()
    result.update(q=[1,16,1536], k=[1,16,256])
    return result


def output_inventory():
    result = {'phase_%d_%s_recipe.f32le'%(i,name):16*width*4 for i,(name,width) in enumerate(STAGES)}
    result.update({name+'.f32le':4*math.prod(shape) for name,shape in shapes().items()
                   if name in ('cache_k','cache_v','scores','logits','softmax_fp32','prob','silu')})
    return result


def record(value, *, size=None, expected=None):
    exact(value, ('path','bytes','sha256'), 'exact fresh file record required')
    name = value['path']
    need(type(name) is str and name and '\\' not in name and '\x00' not in name,
         'invalid fresh artifact path')
    path = PurePosixPath(name)
    need(not path.is_absolute() and all(p not in ('', '.', '..') for p in name.split('/')),
         'fresh artifact path must be a normalized workspace-relative path')
    need(type(value['bytes']) is int and 0 <= value['bytes'] <= ARENA_BYTES and digest(value['sha256']),
         'fresh artifact size/hash type')
    need(size is None or value['bytes'] == size, 'fresh artifact exact byte count')
    need(expected is None or value['sha256'] == expected, 'fresh artifact pinned content hash')


def validate_manifest(value, *, rows=16):
    """Pure schema validation. No imports, source reads or referenced file access."""
    need(type(rows) is int and rows == 16, 'fresh profile supports canonical M16 only')
    exact(value, ('schema','status','profile','rows','past_tokens','source_sha256',
                 'source_manifest_sha256','payload','readonly','sequential','reduced','native','library'),
          'exact fresh manifest schema required')
    need(type(value['schema']) is int and value['schema'] == 1 and value['profile'] == PROFILE and
         value['status'] == STATUS and type(value['rows']) is int and value['rows'] == 16 and
         type(value['past_tokens']) is int and value['past_tokens'] == 0,
         'canonical fresh M16/past-zero profile required')
    need(type(value['source_sha256']) is dict and value['source_sha256'] and
         all(type(k) is str and k and '\\' not in k and '\x00' not in k and not PurePosixPath(k).is_absolute() and
             all(p not in ('', '.', '..') for p in k.split('/')) and digest(v)
             for k,v in value['source_sha256'].items()) and digest(value['source_manifest_sha256']),
         'fresh source manifest types')
    need(sha(encoded(value['source_sha256'])) == value['source_manifest_sha256'],
         'fresh source manifest digest')
    payload = value['payload']; exact(payload, ('manifest','tensors'), 'fresh payload schema')
    record(payload['manifest']); need(payload['manifest']['bytes'] <= MAX_METADATA_BYTES, 'payload metadata bound')
    exact(payload['tensors'], TENSOR_PINS, 'exact thirteen pinned raw tensors required')
    for name,pin in TENSOR_PINS.items():
        record(payload['tensors'][name], size=pin['bytes'], expected=pin['sha256'])
    ro = value['readonly']; exact(ro, ('arena','table','input_x','input_x_sha256','intermediate_preloads'), 'readonly schema')
    record(ro['arena'], size=ARENA_BYTES, expected=ARENA_SHA256)
    record(ro['table'], size=(192+5*16384)*4, expected=TABLE_SHA256)
    record(ro['input_x'], size=16*1536*4, expected=INPUT_X_SHA256)
    need(ro['input_x_sha256'] == INPUT_X_SHA256 and type(ro['intermediate_preloads']) is int and
         ro['intermediate_preloads'] == 0, 'raw input or zero-preload policy drift')
    for role in ('sequential','reduced'):
        producer = value[role]
        keys = ('producer','cpp','header','executable','compile','run','outputs')
        if role == 'sequential': keys += ('tensors','export_receipt')
        exact(producer, keys, 'exact reference producer schema')
        need(producer['producer'] == PRODUCERS[role], 'reference producer role differs')
        for key in ('cpp','header','executable','compile','run'): record(producer[key])
        record(producer['cpp'], expected=CPP_SHA256[role]); record(producer['header'], expected=HEADER_SHA256)
        need(producer['compile']['bytes'] <= MAX_METADATA_BYTES and producer['run']['bytes'] <= MAX_METADATA_BYTES,
             'bounded producer receipt required')
        exact(producer['outputs'], output_inventory(), 'exact twenty-two producer outputs required')
        for name,size in output_inventory().items(): record(producer['outputs'][name], size=size)
        if role == 'sequential':
            record(producer['export_receipt']); need(producer['export_receipt']['bytes'] <= MAX_METADATA_BYTES, 'export metadata bound')
            exact(producer['tensors'], shapes(), 'exact twenty-nine sequential exports required')
            for name,shape in shapes().items(): record(producer['tensors'][name], size=4*math.prod(shape))
    native=value['native']; exact(native, ('producer','result','outputs'), 'native producer schema')
    need(native['producer'] == NATIVE_PRODUCER, 'original native producer required')
    record(native['result']); need(native['result']['bytes'] <= MAX_METADATA_BYTES, 'native metadata bound')
    exact(native['outputs'], MODES, 'both native precision modes required')
    for mode in MODES:
        exact(native['outputs'][mode], METHODS, 'both original reference methods required')
        for method in METHODS:
            exact(native['outputs'][mode][method], shapes(), 'exact twenty-nine native exports required')
            for name,shape in shapes().items(): record(native['outputs'][mode][method][name], size=4*math.prod(shape))
    exact(value['library'], ('receipt','binary'), 'strict official library schema')
    for item in value['library'].values(): record(item)
    need(value['library']['receipt']['bytes'] <= MAX_METADATA_BYTES, 'library receipt bound')
    return value


def resolve_artifact(workspace, value):
    """Reject traversal, symlink components and nonregular files before opening."""
    record(value)
    workspace = safe_path(workspace, directory=True)
    path = workspace
    for component in PurePosixPath(value['path']).parts:
        path = path / component
        mode = path.lstat().st_mode
        need(not stat.S_ISLNK(mode), 'fresh artifact symlink rejected')
    need(path.resolve(strict=True).is_relative_to(workspace) and stat.S_ISREG(path.lstat().st_mode),
         'fresh artifact must be a regular file below workspace')
    need(path.stat().st_size == value['bytes'], 'fresh artifact size drift')
    return path


def safe_path(path, *, directory=False):
    """Inspect every lexical component before resolving the selected root."""
    path = Path(path).absolute()
    need('..' not in path.parts, 'noncanonical fresh workspace path')
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        need(not stat.S_ISLNK(current.lstat().st_mode), 'fresh workspace symlink rejected')
    mode = path.lstat().st_mode
    need(stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode), 'fresh path kind differs')
    return path.resolve(strict=True)


def json_bytes(raw, *, limit=MAX_METADATA_BYTES):
    need(type(raw) is bytes and len(raw) <= limit, 'fresh JSON byte bound')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate fresh JSON key')
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError('nonfinite fresh JSON value')
    def finite_float(value):
        number = float(value)
        need(math.isfinite(number), 'nonfinite fresh JSON numeric overflow')
        return number
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=nonfinite, parse_float=finite_float)


def read_json(path, *, limit=MAX_METADATA_BYTES):
    path = safe_path(path)
    need(path.stat().st_size <= limit, 'fresh JSON byte bound')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    return json_bytes(raw, limit=limit)


def read_manifest(path, expected_sha256, *, rows=16):
    need(type(rows) is int and rows == 16, 'fresh profile supports canonical M16 only')
    need(digest(expected_sha256), 'fresh manifest digest required')
    path = safe_path(path)
    need(path.stat().st_size <= MAX_MANIFEST_BYTES, 'fresh manifest byte bound')
    with path.open('rb') as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    need(len(raw) <= MAX_MANIFEST_BYTES and sha(raw) == expected_sha256, 'fresh manifest hash drift')
    return validate_manifest(json_bytes(raw, limit=MAX_MANIFEST_BYTES), rows=rows)


def checked_artifact(workspace, value):
    path = resolve_artifact(workspace, value)
    need(file_sha(path) == value['sha256'], 'fresh artifact content drift')
    return path


def reject_aliases(workspace, groups):
    """Cross-role source/output paths and (device,inode) pairs must be disjoint."""
    paths, inodes = {}, {}
    for role, records in groups.items():
        for value in records:
            path = resolve_artifact(workspace, value); info = path.stat(); identity = (info.st_dev, info.st_ino)
            need(path not in paths and identity not in inodes, 'fresh artifact path/inode alias rejected')
            paths[path] = role; inodes[identity] = role
    return True


def own_sources():
    need(file_sha(Path(__file__)) == IMPORTED_SOURCE_SHA256, 'loaded fresh verifier source drift')
    return {str((HERE/name).relative_to(ROOT)):file_sha(safe_path(HERE/name)) for name in OWN_INPUTS}


def source_snapshot(*, enable_raw_kv=False):
    """Exact selected source composition, including producer and verifier closure."""
    need(type(enable_raw_kv) is bool, 'canonical raw KV source mode required')
    own_sources()
    pins = read_json(HERE / 'pins.json')
    mode = 'enabled' if enable_raw_kv else 'disabled'
    expected = dict(pins['source_sha256'])
    expected.update(pins['generated_sha256'][mode])
    need(set(pins['source_paths']) == set(expected) | set(pins['own_sources']),
         'fresh source closure scope differs')
    for name, value in expected.items():
        need(file_sha(safe_path(ROOT / name)) == value, 'fresh source composition drift: ' + name)
    return {name:file_sha(safe_path(ROOT / name)) for name in pins['source_paths']}


def fresh_mode(enabled, manifest=None, manifest_sha256=None, *, rows=None):
    need(type(enabled) is bool, 'canonical fresh profile flag required')
    if enabled:
        need(manifest is not None and digest(manifest_sha256), 'fresh manifest path and digest required')
        need(rows is None or (type(rows) is int and rows == 16), 'fresh profile supports canonical M16 only')
    else:
        need(manifest is None and manifest_sha256 is None, 'fresh arguments require explicit fresh profile')
    return enabled


def snapshot_mode(snapshot, enabled, *, enable_raw_kv=False):
    need(type(enabled) is bool and type(enable_raw_kv) is bool, 'canonical snapshot profiles required')
    if enabled:
        need(snapshot.get('fresh_profile') is True and type(snapshot.get('fresh_assets')) is dict,
             'snapshot fresh profile mismatch')
        identity = snapshot['fresh_assets']
        exact(identity, ('profile','manifest','manifest_sha256','enable_raw_kv'), 'fresh snapshot identity schema')
        need(identity['profile'] == PROFILE and type(identity['enable_raw_kv']) is bool and
             identity['enable_raw_kv'] == enable_raw_kv, 'fresh snapshot source profile mismatch')
        fresh_mode(True, identity['manifest'], identity['manifest_sha256'], rows=snapshot['rows'])
        return identity
    need('fresh_profile' not in snapshot and 'fresh_assets' not in snapshot, 'snapshot fresh profile mismatch')
    return None


def metadata(workspace, item, *, limit=MAX_METADATA_BYTES):
    path = resolve_artifact(workspace, item)
    need(item['bytes'] <= limit, 'fresh private metadata byte bound')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    need(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'fresh metadata content drift')
    return json_bytes(raw, limit=limit)


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


def _finite_seconds(value, maximum=None):
    need(type(value) in (int,float) and math.isfinite(value) and value >= 0 and
         (maximum is None or value <= maximum), 'fresh producer time bound/type')


def _verify_payload(workspace, manifest):
    payload = manifest['payload']
    value = metadata(workspace, payload['manifest'])
    ledger_path = safe_path(ROOT / LEDGER)
    need(file_sha(ledger_path) == LEDGER_SHA256, 'original payload ledger drift')
    ledger = read_json(ledger_path)
    bundle = read_json(ROOT / 'config/upstream/weight_headers/qwen2_1p5b/manifest.json')
    need(len(bundle['shards']) == 1, 'original checkpoint shard count differs')
    shard = bundle['shards'][0]
    for key in ('schema_version','model_id','revision','layer_id','header_sha256',
                'payload_bytes','layer_bytes','embedding_bytes'):
        need(same(value.get(key),ledger[key]), 'fresh payload identity differs')
    need(value['status'] == 'ACQUIRED_PINNED_QWEN2_LAYER0_AND_EMBEDDING_ROWS_ONLY' and
         value['full_checkpoint_sha256_verified'] is False and value['official_forward_executed'] is False and
         value['rtl_executed'] is False and value['advertised_full_checkpoint_sha256_unverified'] ==
         shard['advertised_lfs_sha256_unverified'], 'fresh payload acquisition scope differs')
    need(type(value['tensors']) is list and len(value['tensors']) == 13, 'fresh acquired tensor count')
    parent = resolve_artifact(workspace, payload['manifest']).parent
    for actual, expected in zip(value['tensors'], ledger['tensors'], strict=True):
        for key, val in expected.items():
            if key != 'segments':
                need(same(actual.get(key),val), 'fresh acquired tensor metadata drift')
        name = expected['local_name']; item = payload['tensors'][name]
        need(actual['file'] == name + '.bin' and resolve_artifact(workspace, item) == parent / actual['file'] and
             type(actual['http_ranges']) is list and len(actual['http_ranges']) == len(expected['segments']),
             'fresh acquired file/range inventory differs')
        for receipt, segment in zip(actual['http_ranges'], expected['segments'], strict=True):
            need(type(receipt.get('status')) is int and receipt['status'] == 206 and
                 receipt['requested_url'] == shard['url'] and
                 receipt['content_range'] == 'bytes %d-%d/%d' % (segment['start'],segment['end'],shard['file_bytes']) and
                 receipt['request_range'] == 'bytes=%d-%d' % (segment['start'], segment['end']) and
                 same(receipt['bytes'],segment['bytes']) and receipt['sha256'] == segment['sha256'],
                 'fresh bounded HTTP provenance differs')
    return value


def _verify_producer(workspace, manifest, role, compiler, rms):
    producer = manifest[role]
    built = metadata(workspace, producer['compile'])
    exact(built, ('schema','status','producer','argv','compiler','returncode','source_sha256',
                  'cpp_sha256','header_sha256','binary_sha256','elapsed_seconds','requested_timeout_seconds'),
          'exact fresh reference compile receipt required')
    need(type(built['schema']) is int and built['schema'] == 1 and built['status'] == 'COMPILED' and
         built['producer'] == PRODUCERS[role] and type(built['returncode']) is int and built['returncode'] == 0 and
         built['source_sha256'] == manifest['source_sha256'] and built['compiler'] == compiler,
         'fresh reference compile identity differs')
    cpp, header, binary = (resolve_artifact(workspace, producer[k]) for k in ('cpp','header','executable'))
    need(cpp.name == 'candidate.cpp' and header == cpp.parent / 'block_layout.h' and
         built['argv'] == [compiler['path'],'-O2','-std=c++17','-ffp-contract=off','-fno-fast-math',str(cpp),'-o',str(binary)] and
         built['cpp_sha256'] == CPP_SHA256[role] and built['header_sha256'] == HEADER_SHA256 and
         built['binary_sha256'] == producer['executable']['sha256'], 'fresh reference strict compiler invocation differs')
    with binary.open('rb') as stream:
        need(stream.read(4) == b'\x7fELF', 'fresh reference executable is not ELF')
    _finite_seconds(built['elapsed_seconds']); _finite_seconds(built['requested_timeout_seconds'], 10)
    need(built['requested_timeout_seconds'] > 0, 'positive compile timeout required')
    run = metadata(workspace, producer['run'])
    exact(run, ('schema','status','producer','argv','returncode','software_ack','readonly_sha256',
                'input_x_sha256','table_sha256','output_sha256','actual_chain_executed','stdout','empty_cache',
                'elapsed_seconds','requested_timeout_seconds'), 'exact fresh reference run receipt required')
    need(type(run['schema']) is int and run['schema'] == 1 and run['status'] == 'COMPLETE_REFERENCE_ONLY' and
         run['producer'] == PRODUCERS[role] and type(run['returncode']) is int and run['returncode'] == 0 and
         run['actual_chain_executed'] is False and run['readonly_sha256'] == ARENA_SHA256 and
         run['input_x_sha256'] == INPUT_X_SHA256 and run['table_sha256'] == TABLE_SHA256 and
         run['output_sha256'] == {name:item['sha256'] for name,item in producer['outputs'].items()},
         'fresh reference run binding differs')
    record(run['stdout']); need(run['stdout']['bytes'] <= MAX_STDOUT_BYTES, 'bounded software stdout required')
    record(run['empty_cache'], size=0, expected=sha(b''))
    stdout_path = checked_artifact(workspace, run['stdout']); empty = checked_artifact(workspace, run['empty_cache'])
    output_paths = {name:resolve_artifact(workspace,item) for name,item in producer['outputs'].items()}
    directories = {path.parent for path in output_paths.values()}
    need(len(directories) == 1 and all(path.name == name for name,path in output_paths.items()), 'producer output layout differs')
    directory = next(iter(directories))
    need(directory.name == 'raw_stages' and {p.name for p in directory.iterdir()} == set(output_inventory()),
         'producer raw directory inventory differs')
    need(run['argv'] == [str(binary),str(resolve_artifact(workspace,manifest['readonly']['arena'])),
                        '16',str(directory),'0',str(empty),str(empty)], 'fresh reference cold command differs')
    with stdout_path.open('rb') as stream:
        raw = stream.read(MAX_STDOUT_BYTES + 1)
    need(len(raw) == run['stdout']['bytes'] and sha(raw) == run['stdout']['sha256'], 'fresh completion stdout drift')
    need(rms.software_ack(raw.decode('utf-8'),16,run['returncode']) == run['software_ack'], 'fresh software completion differs')
    _finite_seconds(run['elapsed_seconds']); _finite_seconds(run['requested_timeout_seconds'],30)
    need(run['requested_timeout_seconds'] > 0, 'positive reference timeout required')
    return built, run, directory


def _verify_exports(workspace, manifest):
    producer = manifest['sequential']; exported = metadata(workspace, producer['export_receipt'])
    need(type(exported) is list and len(exported) == 29, 'authentic sequential export count')
    need([r.get('name') for r in exported] == sorted(shapes()), 'authentic sequential export order')
    for item in exported:
        exact(item, ('name','path','shape','export_shape','sha256'), 'original export record schema')
        name = item['name']; actual = producer['tensors'][name]
        need(item['path'] == 'candidate_' + name + '.f32le' and same(item['shape'],shapes()[name]) and
             same(item['export_shape'],export_shapes()[name]) and item['sha256'] == actual['sha256'] and
             resolve_artifact(workspace,actual).name == item['path'], 'authentic sequential export binding differs')
    return exported


def _verify_native(workspace, manifest, native):
    result = metadata(workspace,manifest['native']['result'])
    need(type(result.get('schema_version')) is int and result['schema_version'] == 1 and
         result['status'] == 'PASS_BF16_STAGE_BUDGET' and
         result['model_id'] == MODEL and type(result['layer']) is int and result['layer'] == 0 and
         type(result['tokens']) is int and result['tokens'] == 16 and result['carried'] is False and
         result['m16_gate_sha256'] is None and type(result['torch_threads']) is int and result['torch_threads'] == 4 and
         result['payload_manifest_sha256'] == manifest['payload']['manifest']['sha256'] and
         result['official_framework_forward'] is True and result['rtl_execution'] is False and
         result['hardware_recipe_acceptance'] is False and result['logits'] is False and
         result['full_model_quality'] is False and result['manifest_whole_checkpoint_hash_verified'] is False,
         'fresh official producer scope differs')
    _, identity = native.runtime_identity(ROOT)
    # Match the producer's JSON representation (e.g. TorchVersion is a str
    # subclass), while retaining canonical JSON bool/int distinctions.
    identity = json_bytes(encoded(identity))
    need(same(result['identity'],identity) and same(result['policy'],native.load_policy(ROOT)),
         'fresh native runtime/source/threshold identity differs')
    exact(result['modes'],MODES,'fresh native precision modes differ')
    root = resolve_artifact(workspace,manifest['native']['result']).parent
    semantics = ('mask_exact','native_fp32_probability_sum_within_2e_5',
        'independent_fp32_probability_sum_within_2e_5','native_cache_append_k_exact',
        'native_cache_append_v_exact','independent_cache_append_k_exact','independent_cache_append_v_exact',
        'native_future_probability_zero','independent_future_probability_zero')
    for mode in MODES:
        phases = result['modes'][mode]['phases']
        need(type(phases) is list and len(phases) == 1, 'fresh native cold phase count')
        phase = phases[0]
        need(type(phase['phase']) is int and phase['phase'] == 0 and type(phase['past_tokens']) is int and
             phase['past_tokens'] == 0 and phase['token_ids'] == phase['position_ids'] == list(range(16)) and
             all(type(i) is int for i in phase['token_ids'] + phase['position_ids']), 'fresh native workload identity differs')
        exact(phase['semantics'],semantics,'fresh native semantic inventory differs')
        need(all(v is True for v in phase['semantics'].values()) and phase['all_semantics_exact'] is True,
             'fresh native semantic checks incomplete')
        exact(phase['stages'],shapes(),'fresh native stage inventory differs')
        failures = []
        for name, item in phase['stages'].items():
            need(same(item['shape'],shapes()[name]) and same(item['elements'],math.prod(shapes()[name])) and
                 item['finite'] is True, 'fresh native logical geometry differs')
            need(type(item['bit_exact']) is bool, 'fresh native bit-exact flag must be boolean')
            verdict = native.stage_verdict(name,item,mode,result['policy'])
            need(all(same(item.get(key),value) for key,value in verdict.items()), 'fresh native stage verdict differs')
            if item['passed'] is False:
                failures.append(name)
            for method, prefix in zip(METHODS,('native','independent'),strict=True):
                record_ = manifest['native']['outputs'][mode][method][name]
                expected_path = '%s/phase_0/%s_%s.f32le' % (mode,prefix,name)
                need(item[prefix+'_file'] == expected_path and
                     same(item[prefix+'_export_shape'],export_shapes()[name]) and
                     item[prefix+'_file_sha256'] == record_['sha256'] and
                     resolve_artifact(workspace,record_) == root / expected_path,
                     'fresh native export path/layout/hash differs')
        need(phase['failed_stages'] == failures, 'fresh native diagnostic failures changed')
        expected = ('FAIL_BF16_STAGE_BUDGET' if failures else 'PASS_BF16_STAGE_BUDGET') if mode == 'bf16' else 'DIAGNOSTIC_FP32'
        need(phase['status'] == expected, 'fresh native phase status differs')
        _finite_seconds(phase['seconds']); _finite_seconds(result['modes'][mode]['seconds'])
    need(result['status'] == result['modes']['bf16']['phases'][0]['status'], 'fresh native terminal status differs')
    _finite_seconds(result['seconds'])
    return result


def _views(workspace, path, expected_sha256, manifest, exported, native_result, directories, *, enable_raw_kv):
    def absolute(item):
        return str(resolve_artifact(workspace,item))
    role_names = {'embeddings':'embed_tokens.rows_0_255','gamma0':'input_layernorm.weight',
        'gamma1':'post_attention_layernorm.weight', 'wq':'self_attn.q_proj.weight','bq':'self_attn.q_proj.bias',
        'wk':'self_attn.k_proj.weight','bk':'self_attn.k_proj.bias','wv':'self_attn.v_proj.weight',
        'bv':'self_attn.v_proj.bias','wo':'self_attn.o_proj.weight','wg':'mlp.gate_proj.weight',
        'wu':'mlp.up_proj.weight','wd':'mlp.down_proj.weight'}
    comparison_records = list(manifest['sequential']['outputs'].values()) + list(manifest['sequential']['tensors'].values())
    comparison_records += list(manifest['reduced']['outputs'].values()) + list(records(manifest['native']['outputs']))
    original_input = dict(token_ids=list(range(16)),positions=list(range(16)),input_x_sha256=INPUT_X_SHA256,
        intermediate_preloads=0,rope_theta=1000000.0,
        rope_table_recipe='FP32 exponent/powf/reciprocal/phase multiply/sinf/cosf then BF16; positions0..255 only',
        readonly_bytes=ARENA_BYTES,readonly_sha256=ARENA_SHA256)
    spec = dict(model=MODEL,revision=REVISION,layer=0,original_input=original_input,
        fresh_profile=PROFILE,metadata_sha256={str(path):expected_sha256},payloads={
            role:dict(path=absolute(manifest['payload']['tensors'][name]),bytes=TENSOR_PINS[name]['bytes'],
                      sha256=TENSOR_PINS[name]['sha256'],shape=TENSOR_PINS[name]['shape']) for role,name in role_names.items()},
        comparison_only={str(i):dict(item,path=absolute(item)) for i,item in enumerate(comparison_records)},
        oracle_arena=dict(manifest['readonly']['arena'],path=absolute(manifest['readonly']['arena'])))
    lookup = {'raw_stages/'+name:item for name,item in manifest['sequential']['outputs'].items()}
    lookup.update({'tensors/candidate_'+name+'.f32le':item for name,item in manifest['sequential']['tensors'].items()})
    for method in METHODS:
        lookup.update({'references/%s/%s.f32le'%(method,name):item
                       for name,item in manifest['native']['outputs']['bf16'][method].items()})
    identity = dict(profile=PROFILE,manifest=str(path),manifest_sha256=expected_sha256,enable_raw_kv=enable_raw_kv)
    provenance = dict(profile=PROFILE,fresh_assets=identity,new_official_forward_executed=True,
        historical_receipts_reused=False,actual_chain_executed=False,
        native_result_sha256=manifest['native']['result']['sha256'],native_status=native_result['status'],
        native_vs_independent_failed_stages=native_result['modes']['bf16']['phases'][0]['failed_stages'],
        producer_sha256=manifest['source_sha256']['scripts/qwen2_layer0_model_gate.py'],
        sequential_cpp_sha256=CPP_SHA256['sequential'],reduced_cpp_sha256=CPP_SHA256['reduced'])
    reference = dict(fresh_profile=PROFILE,workspace=str(workspace),directory=str(resolve_artifact(workspace,manifest['readonly']['table']).parent),
        table_path=absolute(manifest['readonly']['table']),fresh_lookup=lookup,inputs=dict(original_input,position_ids=list(range(16))),
        threshold_policy=native_result['policy'],official_reference_identity=native_result['identity'],
        tensors=exported,prior_failures={},
        fresh_provenance=provenance,artifacts=[dict(item,path=name) for name,item in lookup.items()],
        native_execution_reused=False,oracle_execution_reused=False,old_pass_inherited=False)
    reduced = dict(fresh_profile=PROFILE,workspace=str(workspace),directory=str(directories['reduced'].parent),rows=16,past_tokens=0,
        result_sha256=manifest['reduced']['run']['sha256'],readonly_input=dict(path=absolute(manifest['readonly']['arena']),
        bytes=ARENA_BYTES,sha256=ARENA_SHA256,input_x_sha256=INPUT_X_SHA256),
        fresh_lookup={'raw_stages/'+name:item for name,item in manifest['reduced']['outputs'].items()},
        artifacts=[dict(item,path='raw_stages/'+name) for name,item in manifest['reduced']['outputs'].items()],
        actual_chain_executed=False,native_acceptance=False,fresh_provenance=provenance)
    return dict(input_spec=spec,reference=reference,independent_reference=reduced,provenance=provenance,
                library_receipt=absolute(manifest['library']['receipt']),library=absolute(manifest['library']['binary']))


def verify(path, expected_sha256, *, rows=16, enable_raw_kv=False):
    """Hash-only asset admission before any reference numerical array is loaded."""
    need(type(enable_raw_kv) is bool, 'canonical raw KV source mode required')
    manifest = read_manifest(path,expected_sha256,rows=rows)
    path = safe_path(path); workspace = safe_path(path.parent,directory=True)
    before = source_snapshot(enable_raw_kv=enable_raw_kv)
    need(manifest['source_sha256'] == before, 'fresh producer source closure differs')
    # Hash all declared bytes before importing any producer/runtime helper.
    for item in records(manifest):
        checked_artifact(workspace,item)
    reject_aliases(workspace,{role:list(records(manifest[role])) for role in
                             ('payload','readonly','sequential','reduced','native','library')})
    _verify_payload(workspace,manifest)
    from candidates.qwen2_resident_matrix.official_bf16 import dense_silu
    from scripts import qwen2_rms_rope_prefill_candidate as rms
    from scripts import qwen2_layer0_model_gate as native
    library = metadata(workspace,manifest['library']['receipt'])
    need(type(library.get('returncode')) is int and library['returncode'] == 0 and
         library['library'] == str(resolve_artifact(workspace,manifest['library']['binary'])) and
         library['library_sha256'] == manifest['library']['binary']['sha256'], 'fresh strict ELF receipt binding differs')
    dense_silu.verify_library(library)
    directories = {}
    for role in ('sequential','reduced'):
        _,_,directories[role] = _verify_producer(workspace,manifest,role,library['compiler'],rms)
    need(directories['sequential'] != directories['reduced'] and
         (directories['sequential'].stat().st_dev,directories['sequential'].stat().st_ino) !=
         (directories['reduced'].stat().st_dev,directories['reduced'].stat().st_ino), 'fresh producer directories alias')
    exported = _verify_exports(workspace,manifest)
    native_result = _verify_native(workspace,manifest,native)
    need(before == source_snapshot(enable_raw_kv=enable_raw_kv), 'fresh source changed during admission')
    need(read_manifest(path,expected_sha256,rows=rows) == manifest, 'fresh manifest changed during admission')
    for item in records(manifest):
        checked_artifact(workspace,item)
    return _views(workspace,path,expected_sha256,manifest,exported,native_result,directories,enable_raw_kv=enable_raw_kv)


def read_reference_bytes(reference, relative):
    """Comparison-only: call solely after the original whole-terminal gate opens."""
    need(reference.get('fresh_profile') == PROFILE and relative in reference['fresh_lookup'],
         'fresh reference lookup outside sealed inventory')
    item = reference['fresh_lookup'][relative]
    path = resolve_artifact(reference['workspace'],item)
    raw = path.read_bytes()
    need(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'fresh comparison payload drift')
    return raw


def read_native_reference(reference, raw, *, rows, method, name, shape):
    """Late original decoder; fresh producer metadata fixes token-major Q/K."""
    need(type(rows) is int and rows == 16 and method in METHODS and name in shapes() and
         tuple(shape) == tuple(shapes()[name]), 'fresh reference logical layout differs')
    item = reference['fresh_lookup']['references/%s/%s.f32le'%(method,name)]
    need(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'fresh native comparison bytes differ')
    from candidates.qwen2_resident_matrix.official_bf16.reference_layout import decode_qk
    if name in ('q','k'):
        return decode_qk(raw,shape,'token_major')
    import numpy as np
    return np.frombuffer(raw,dtype='<f4').reshape(shape)
