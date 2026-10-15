"""Cold CI adapter for unchanged official full29 arithmetic. Review is external."""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CI_ROOT = Path('/home/runner/work/hetero_cnn_llm_aha/hetero_cnn_llm_aha')
PACKAGE = 'candidates/qwen2_fullblock_ci_reference'
OLD = 'candidates/qwen2_fullblock_reference_m128'
WORK = 'work/qwen2_fullblock_ci_reference'
BINDING = WORK+'/BINDINGS.json'
PREFIX = 'work/qwen2_live_qkv_inputs_m128/ci01'
TAIL = 'work/qwen2_live_tail_acquisition_m128/ci01'
INPUT_PATHS = dict(prefix_raw=PREFIX+'/raw/subset_manifest.json',
    prefix_ready=PREFIX+'/inputs/INPUTS_READY.json',tail_raw=TAIL+'/raw/FRESH_ACQUISITION.json',
    tail_ready=TAIL+'/inputs/INPUTS_READY.json')
PYTHON_PREFIX = Path('/opt/hostedtoolcache/Python/3.12.14/x64')
PYTHON_IDENTITY = dict(bytes=17752,
    sha256='bef88f140b625959f8af25c7b75cce2cd5d4b29cc2f2b079befd7f68eda4dba0')
HISTORICAL_WORK_SOURCES = frozenset((
    'work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/bootstrap/BOOTSTRAP_REFERENCE.json',
    'work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/bootstrap/SEAL.json',
    'work/qwen2_fullblock_reference_capture_review_20261014/bootstrap_v2_review/BOOTSTRAP_REVIEW.json',
    'work/qwen2_fullblock_reference_map_20261014/AUDIT.json',
    'work/qwen2_fullblock_reference_map_20261014/REPORT.md',
    'work/qwen2_fullblock_reference_map_20261014/SEAL.json',
    'work/qwen2_fullblock_reference_map_20261014/official_dependency/SOURCE_RECEIPT.json',
    'work/qwen2_fullblock_reference_map_20261014/official_dependency/activations.py',
    'work/qwen2_live_attention_reference_m128/control/frozen01/CAPTURE_EXECUTION.json',
    'work/qwen2_live_attention_reference_m16_20261014/bootstrap01/control/RESULT.json',
    'work/qwen2_live_qkv_inputs_m128/frozen01/inputs/INPUTS_READY.json',
    'work/qwen2_live_qkv_inputs_m128/frozen01/raw/subset_manifest.json',
    'work/qwen2_live_tail_inputs_m128/reconstruct01/inputs/INPUTS_READY.json',
    'work/qwen2_tail_inputs_independent_review_20261014/REPORT.md',
    'work/qwen2_tail_ranges_20261014/tail_manifest.json',
))
_modules = {}

def sha(raw): return hashlib.sha256(raw).hexdigest()

class Rejected(ValueError): pass

def need(ok, message):
    if not ok: raise Rejected(message)

def dependency(path):
    specs = json.loads((HERE/'dependencies.json').read_bytes())
    need(path in specs, 'unlisted source dependency')
    source = ROOT/path
    raw = source.read_bytes()
    need(source.resolve() == source and not source.is_symlink() and
         len(raw) == specs[path]['bytes'] and sha(raw) == specs[path]['sha256'], 'source dependency drift: '+path)
    if path not in _modules:
        spec = importlib.util.spec_from_file_location('_ci_full29_'+sha(path.encode())[:16],source)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        _modules[path] = mod
    return _modules[path]

def legacy(name): return dependency(OLD+'/'+name)
O = legacy('recipe.py')
Rejected = O.Rejected
same,fields,exact_keys,encoded,parse = O.same,O.fields,O.exact_keys,O.encoded,O.parse
safe_path,checked,stat_only = O.safe_path,O.checked,O.stat_only
require_supported_python,official_nodes = O.require_supported_python,O.official_nodes
validate_observations = O.validate_observations
MODEL_SOURCE,ACTIVATION_SOURCE = O.MODEL_SOURCE,O.ACTIVATION_SOURCE
NAMES,TOKEN_MAJOR,PINS_SHA256 = O.NAMES,O.TOKEN_MAJOR,O.PINS_SHA256

def identity(path):
    raw = path.read_bytes()
    return dict(bytes=len(raw),sha256=sha(raw))

def observed_python():
    need(sys.implementation.name == 'cpython' and sys.version_info[:3] == (3,12,14), 'fixed CI Python version')
    path = Path(sys.executable).resolve(strict=True)
    need(path.is_relative_to(PYTHON_PREFIX) and path.is_file(), 'observed setup-python executable required')
    actual = identity(path)
    need(same(actual,PYTHON_IDENTITY), 'observed CI Python ELF identity drift')
    return dict(path=str(path),**actual)

def runtime_pins(root=ROOT):
    need(root == CI_ROOT and root == ROOT, 'exact CI checkout root required')
    pins = dependency('candidates/qwen2_fullblock_ci_execution/runtime_profile.py').apply(O.load_pins(root))
    pins['capture_environment']['PYTHONPATH'] = str(root/'work/runtime_recovery/site-packages')
    pins['runtime_native_files']['python'] = observed_python()
    # The other five native files and all numerical runtime requirements remain exact.
    return pins

def bootstrap_policy():
    """The reviewed procedure, not approval of as-yet-unobserved receipt bytes."""
    original = dependency('candidates/qwen2_fullblock_ci_execution/runtime_profile.py').apply(O.load_pins(ROOT))
    result = dict(schema=1,kind='SOURCE_POLICY_FOR_ONE_NEW_PLATFORM_BOOTSTRAP',root=str(CI_ROOT),
        input_paths=INPUT_PATHS,output_namespace=WORK,original_pins_sha256=O.PINS_SHA256,
        python=dict(resolved_path_within=str(PYTHON_PREFIX),version=[3,12,14],**PYTHON_IDENTITY),
        other_native_files={k:v for k,v in original['runtime_native_files'].items() if k!='python'},
        runtime_requirements=original['runtime_requirements'],
        observed_bindings_independently_reviewed=False,
        output_scope='SEALED_BOOTSTRAP_OBSERVATIONS_UNACCEPTED',
        frozen_mode_available=False,numerical_acceptance_allowed=False)
    if original['capture_environment']['ATEN_CPU_CAPABILITY'] is not None:
        result['aten_dispatch_environment'] = original['capture_environment']['ATEN_CPU_CAPABILITY']
    profile = dependency('candidates/qwen2_fullblock_ci_execution/runtime_profile.py')
    if profile.mkldnn_enabled() is False:
        result['cpu_backend_policy'] = dict(profile=profile.profile(),mkldnn_enabled=False,setting_boundary='official-holder-construction-and-raw-bindings')
    return result

def derive_bindings(root=ROOT):
    """Observe only new metadata. This does not review, approve or authorize it."""
    need(root == ROOT == CI_ROOT, 'binding generation requires exact CI root')
    specs = {key:dict(path=path,**identity(safe_path(root,path))) for key,path in INPUT_PATHS.items()}
    return dict(schema=1,status='OBSERVED_LOCAL_BINDINGS_UNREVIEWED',root=str(root),
        input_metadata=specs,python=observed_python(),
        source_manifest=source_manifest(root),numeric_execution_allowed=False)

def bindings(root=ROOT):
    result = parse(safe_path(root,BINDING).read_bytes())
    need(same(result,derive_bindings(root)), 'fresh local bindings drift')
    return result

def load_pins(root=ROOT):
    b = bindings(root)
    pins = runtime_pins(root)
    # Historical receipts are excluded as provenance, never copied or invented.
    # Runtime Python source files remain pinned. No geometry/math/value pins change.
    original = O.load_pins(root)  # Exact code-pinned original byte digest, not untrusted metadata.
    actual_historical = {p for p in pins['sources'] if p.startswith('work/') and not p.startswith('work/runtime_recovery/')}
    need(actual_historical == HISTORICAL_WORK_SOURCES, 'exact historical source exclusion inventory')
    for path in HISTORICAL_WORK_SOURCES:
        need(same(pins['sources'][path],original['sources'][path]), 'historical source identity drift')
        del pins['sources'][path]
    pins['input_metadata'] = copy.deepcopy(b['input_metadata'])
    for raw in pins['raw_tensors']:
        raw['path'] = str(Path(pins['input_metadata'][raw['manifest_role']]['path']).parent/(raw['local_name']+'.bin'))
    for name,role in pins['producer_roles'].items():
        key = 'tail_ready' if name in ('wo','gamma1','wg','wu','wd') else 'prefix_ready'
        role['path'] = str(Path(pins['input_metadata'][key]['path']).parent/(name+'.bin'))
    for spec in b['input_metadata'].values():
        pins['sources'][spec['path']] = {k:spec[k] for k in ('bytes','sha256')}
    for path,spec in parse((HERE/'dependencies.json').read_bytes()).items():
        pins['sources'][path] = spec
    return pins

def source_manifest(root=ROOT):
    need(root == ROOT, 'exact source root')
    path = HERE/'SOURCE_MANIFEST.json'
    manifest = parse(path.read_bytes())
    exact_keys(manifest,('schema','files'),'CI source manifest')
    need(manifest['schema'] == 1, 'manifest schema')
    present = {str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file()}
    need(present == set(manifest['files'])|{'SOURCE_MANIFEST.json'}, 'exact CI source inventory')
    for name,spec in manifest['files'].items(): checked(root,PACKAGE+'/'+name,spec)
    return identity(path)

def require_frozen_references(*args,**kwargs):
    raise Rejected('CI freeze not reviewed: independent fresh bootstrap review and source-pinned freeze required; historical freeze is not reused')

def metadata_check(root,pins):
    """Metadata/receipt/source reads and payload stat only; no full tail reader."""
    need(same(pins,load_pins(root)), 'fixed CI effective pins required')
    data = {k:parse(checked(root,s['path'],s)) for k,s in pins['input_metadata'].items()}
    Q = dependency('candidates/qwen2_live_qkv_inputs_m128/recipe.py')
    qp = Q.load_pins(root)
    prefix,ready = data['prefix_raw'],data['prefix_ready']
    Q.verify_report(prefix,root,qp,'acquire'); Q.verify_report(ready,root,qp,'materialize')
    fields(prefix,dict(status='RECOVERED_PINNED_QWEN2_PREFIX_SUBSET_ONLY',payload_bytes=7085056,
                       acquisition='fresh_HTTP206'),'fresh QKV')
    need(type(prefix['tensors']) is list and len(prefix['tensors']) == 8,'eight raw prefix tensors')
    proofs = {}
    for item,spec in zip(prefix['tensors'],qp['tensors']):
        fields(item,spec,'prefix tensor'); exact_keys(item,set(spec)|{'http_ranges'},'prefix keys')
        need(type(item['http_ranges']) is list and len(item['http_ranges']) == 1,'one fresh receipt')
        receipt = item['http_ranges'][0]; Q.verify_http(receipt,spec,qp)
        path = PREFIX+'/raw/'+spec['local_name']+'.receipt.json'
        raw = safe_path(root,path).read_bytes()
        need(same(parse(raw),receipt),'standalone prefix receipt')
        proofs[path] = dict(bytes=len(raw),sha256=sha(raw))
    expected_prefix = {'subset_manifest.json'}|{s['file'] for s in qp['tensors']}|{s['local_name']+'.receipt.json' for s in qp['tensors']}
    need({p.name for p in safe_path(root,PREFIX+'/raw').iterdir()} == expected_prefix,'exact prefix inventory')
    T = dependency('candidates/qwen2_fullblock_ci_prepare/fresh_tail.py')
    tail = T.input_metadata(root,TAIL+'/inputs',pins['input_metadata']['tail_ready']['sha256'],
                            pins['input_metadata']['tail_raw']['sha256'])
    need(tail['ready']['subset'] == TAIL+'/raw', 'exact fresh tail subset')
    proofs.update(tail['proof_files'])
    fields(ready,dict(status='PINNED_PREFIX_INPUTS_READY_NO_MODEL_EXECUTION',subset=PREFIX+'/raw',
        subset_manifest_sha256=pins['input_metadata']['prefix_raw']['sha256'],torch_imported=False,
        numpy_imported=False),'prefix input metadata')
    need(len(ready['roles']) == 9 and len(tail['ready']['roles']) == 5,'9+5 producer roles')
    for key,records in (('prefix_ready',ready['roles']),('tail_ready',tail['ready']['roles'])):
        for name,record in records.items():
            spec = pins['producer_roles'][name]
            need(same(record,spec['record']), 'producer role identity: '+name)
            fields(record,{k:spec[k] for k in ('bytes','sha256')},'producer bytes/hash')
            stat_only(root,spec['path'],spec['bytes'])
    directory = safe_path(root,PREFIX+'/inputs')
    need({p.name for p in directory.iterdir()} ==
         {'INPUTS_READY.json','rope_full.f32le','rope_build'}|{n+'.bin' for n in ready['roles']},
         'exact prefix typed inventory')
    need(same(ready['rope'],{**qp['rope'],'file':'rope_full.f32le'}),'exact RoPE metadata')
    need(qp['rope']['bytes'] == 328448,'fixed complete RoPE size')
    stat_only(root,PREFIX+'/inputs/rope_full.f32le',328448)
    build = safe_path(root,PREFIX+'/inputs/rope_build')
    need(build.is_dir() and {p.name for p in build.iterdir()} ==
         {'independent.c','independent.so','build.log'},'exact RoPE build inventory')
    # Preparation already verifies support bytes and compiler provenance. This
    # reader checks their fixed metadata and presence only, with no tool calls.
    record = ready['rope_build']
    exact_keys(record,{'command','source_sha256','binary_sha256','compiler_sha256',
                       'compiler','historical_binary_identity_claimed'},'RoPE build')
    fields(record,dict(command=Q.compile_command(directory),source_sha256=qp['rope_c_source_sha256'],
        historical_binary_identity_claimed=False),'RoPE build source/flags')
    for key in ('source_sha256','binary_sha256','compiler_sha256'):Q.digest(record[key],key)
    need(type(record['compiler']) is str and bool(record['compiler']) and '\n' not in record['compiler'],
         'compiler version line required')
    for name in ('independent.c','independent.so','build.log'):
        path = safe_path(root,PREFIX+'/inputs/rope_build/'+name)
        need(path.is_file() and (name == 'build.log' or path.stat().st_size > 0),'RoPE support file stat')
    all_tensors = prefix['tensors']+data['tail_raw']['tensors']
    need(len({t['local_name'] for t in all_tensors}) == 13,'unique raw13')
    by_name = {t['local_name']:t for t in all_tensors}
    h = checked(root,pins['shard']['header']['path'],pins['shard']['header'])
    need(len(h) == 38536 and int.from_bytes(h[:8],'little')+8 == len(h),'header framing')
    header = parse(h[8:])
    for spec in pins['raw_tensors']:
        item = by_name[spec['local_name']]
        fields(item,{k:spec[k] for k in ('name','local_name','shape','dtype','bytes','sha256','start','end','source_shape','source_data_offsets')},'raw identity')
        need(spec['path'] == str(Path(pins['input_metadata'][spec['manifest_role']]['path']).parent/item['file']),'raw path')
        fields(header[spec['name']],dict(dtype='BF16',shape=spec['source_shape'],data_offsets=spec['source_data_offsets']),'header tensor')
        need(spec['bytes'] == math.prod(spec['shape'])*2 == spec['end']-spec['start']+1 and
             spec['start'] == len(h)+spec['source_data_offsets'][0],'raw range geometry')
        stat_only(root,spec['path'],spec['bytes'])
    return dict(raw_tensors=13,producer_roles=14,raw_payload_read=False,producer_payload_read=False,
        proof_files=proofs,raw_support_files={},fresh_tail_receipts=14,reused_tail_tensors=0)

def check_contract(pins):
    profile = dependency('candidates/qwen2_fullblock_ci_execution/runtime_profile.py')
    if not profile.selected():
        O.check_contract(pins)
        return
    expected = runtime_pins(ROOT)
    need(same(pins['runtime_requirements'], expected['runtime_requirements']),
         'exact AVX2 candidate runtime required')
    need(same(pins['capture_environment'], expected['capture_environment']),
         'exact AVX2 candidate environment required')
    # Validate every unchanged numerical contract with the original validator.
    # This temporary validation projection is never passed to execution/receipt.
    validation = copy.deepcopy(pins)
    validation['runtime_requirements']['capability'] = 'AVX512'
    O.check_contract(validation)


def source_check(root,pins):
    require_supported_python()
    source_manifest(root)
    need(root == ROOT and root.resolve() == ROOT and (root/'.git').exists(), 'exact checkout root required')
    need(same(pins,load_pins(root)), 'effective CI binding drift')
    check_contract(pins)
    for path,spec in pins['sources'].items():
        checked(root,path,spec)
    model = official_nodes(root,pins['model_ast_nodes'],MODEL_SOURCE,pins['sources'])
    activation = official_nodes(root,pins['activation_ast_nodes'],ACTIVATION_SOURCE,pins['sources'])
    for node in pins['torch_boundary_nodes']:
        official_nodes(root,[node],node['path'],pins['sources'])
    ap = parse(checked(root,'candidates/qwen2_live_attention_reference_m128/pins.json',
                       pins['sources']['candidates/qwen2_live_attention_reference_m128/pins.json']))
    # The first 27 records inherit exactly their original AST identities. Labels and
    # source excerpts in the mapping are explanatory and not executable rewrites.
    for actual,expected in zip(pins['model_ast_nodes'][:27],ap['official_ast_nodes']):
        fields(actual,{k:expected[k] for k in ('line_start','line_end','node_type','source_sha256','ast_sha256')},
               'unchanged original27')
    need(same(pins['prior18_expectations'],ap['references']), 'prior18 reproduction expectations drift')
    config = parse(checked(root,pins['config_source'],pins['sources'][pins['config_source']]))
    fields(config,{'hidden_size':1536,'intermediate_size':8960,'hidden_act':'silu',
        'num_attention_heads':12,'num_key_value_heads':2,'rms_norm_eps':1e-6,
        'rope_theta':1000000.0,'max_position_embeddings':32768},'official config')
    source = checked(root,ACTIVATION_SOURCE,pins['sources'][ACTIVATION_SOURCE])
    need(sha(source) == '10c37e915ce2b52d539a5b52ecaaf644e2b0c56d282db00778098d74342ebeee',
         'official activation file hash')
    need(hashlib.sha1(b'blob '+str(len(source)).encode()+b'\0'+source).hexdigest() ==
         '2355fb5fed678d0de6e2c53f52644a35a691a34e', 'official activation Git blob identity')
    mapping = activation[-2]
    need(isinstance(mapping,ast.Assign) and isinstance(mapping.value,ast.Dict), 'whole original ACT2CLS assignment')
    selected = [v for k,v in zip(mapping.value.keys,mapping.value.values)
                if isinstance(k,ast.Constant) and k.value == 'silu']
    need(len(selected) == 1 and ast.dump(selected[0],include_attributes=False) ==
         "Attribute(value=Name(id='nn', ctx=Load()), attr='SiLU', ctx=Load())", 'original silu mapping')
    for label,closure in pins['preserved_execution_closures'].items():
        need(closure['count'] == {'m128':169,'m16':188}[label] == len(closure['sha256']), 'preservation closure size')
        for path,digest in closure['sha256'].items():
            need(sha(safe_path(root,path).read_bytes()) == digest, 'preserved '+label+' source drift: '+path)
    for spec in pins['runtime_native_files'].values():
        path = Path(spec['path']) if Path(spec['path']).is_absolute() else safe_path(root,spec['path'])
        need(path.is_file() and path.stat().st_size == spec['bytes'], 'native runtime stat drift')
    return {**metadata_check(root,pins),'model_ast_nodes':len(model),'activation_ast_nodes':len(activation),
            'reference_nodes':29,'pinned_sources':len(pins['sources']),
            'preserved_m128_sources':169,'preserved_m16_sources':188,'native_runtime_rehashed':False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-bindings',action='store_true')
    args = parser.parse_args(argv)
    source_manifest()
    if args.prepare_bindings:
        value = derive_bindings()
        path = safe_path(ROOT,BINDING);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream: stream.write(encoded(value))
        metadata_check(ROOT,load_pins())
        status = 'LOCAL_BINDINGS_PREPARED_UNREVIEWED'
    else: status = 'NOT_EXECUTED_SOURCE_ONLY'
    print(json.dumps(dict(status=status,model_executed=False,numeric_execution_allowed=False,
        bootstrap_review_required=True,frozen_mode_available=False),sort_keys=True))
    return 0

if __name__ == '__main__': raise SystemExit(main())
