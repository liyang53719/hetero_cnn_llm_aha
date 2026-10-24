"""Current recovered reference/operand binding. No historical execution approval reused."""
import hashlib,json,os,re,stat,sys,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
CANDIDATE=HERE.parents[1]
ROOT=CANDIDATE/'source'
WORK='work/qwen2_fixed93_fullblock_binding'
FROZEN_BINDING=WORK+'/FROZEN_BINDING.json'
REFERENCE='work/qwen2_recovered_reference/first'
REFERENCE_MANIFEST='REFERENCE.json'
CLOSURE_ENV='QWEN2_FIXED93_SOURCE_MANIFEST_SHA256'
BINDING_ENV='QWEN2_FIXED93_FROZEN_BINDING_SHA256'
STATUS='CURRENT_REVIEWED_FROZEN_PAIR_ORACLE_ONLY'
PINS_SHA256='48e20d380cfc6ac0ab5b9e1690bb507e37cf99468b0df8e79a1d37da0f16110f'
FROZEN_CONTRACT_FILE='candidates/qwen2_fullblock_reference_m128/FROZEN_CONTRACT.json'
FROZEN_CONTRACT_SHA256='64835641b2c0c16d83beb75fbcd9d1c83ade8676fbd825f5e6ab646167af723f'
METADATA_NAMES=frozenset(('BOUNDARY_BEFORE.json','BOUNDARY_AFTER.json','WRAPPER_BEFORE.json','WRAPPER_AFTER.json',REFERENCE_MANIFEST,'GO.json','OBSERVATIONS.json','STAGES.jsonl','stdout.log','stderr.log','PACKAGE_ORIGINS.json'))
_LAYOUT=None
_FROZEN_PREFIXES=('work/qwen2_recovered_inputs','work/qwen2_recovered_reference')
class Rejected(ValueError):pass
def need(ok,message):
    if not ok:raise Rejected(message)
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def parse(b):return json.loads(b)
def same(a,b):return type(a) is type(b) and (a.keys()==b.keys() and all(same(a[k],b[k]) for k in a) if isinstance(a,dict) else len(a)==len(b) and all(same(x,y) for x,y in zip(a,b)) if isinstance(a,list) else a==b)
def fields(a,b,label):need(isinstance(a,dict) and all(k in a and same(a[k],v) for k,v in b.items()),label)
def exact_keys(a,keys,label):need(type(a) is dict and set(a)==set(keys),label)
def digest(v):need(type(v) is str and re.fullmatch('[0-9a-f]{64}',v) and v!='0'*64,'explicit SHA256');return v
def frozen_layout():
    global _LAYOUT
    if _LAYOUT is None:
        module=sys.modules.get('assembly_preflight')
        need(type(module) is types.ModuleType and module.__name__=='assembly_preflight' and
             Path(module.__file__)==CANDIDATE/'assembly_preflight.py',
             'canonical source-checked preflight loader required before runtime')
        _LAYOUT=module.frozen_layout()
    return _LAYOUT
def _relative(name):
    need(type(name) is str and name and name!='.','relative pinned path')
    p=Path(name)
    need(not p.is_absolute() and '..' not in p.parts and str(p)==name,'canonical relative pinned path')
    return p
def _frozen_namespace(name):
    return any(name==prefix or name.startswith(prefix+'/') for prefix in _FROZEN_PREFIXES)
def frozen_path(name):
    p=_relative(name);layout=frozen_layout()
    if layout.contains(name):return layout.path(name)
    need(not _frozen_namespace(name),'undeclared frozen logical path: '+name)
    need(p.parts[0]!='work' or name==FROZEN_BINDING,'undeclared local work path: '+name)
    p=ROOT/p;need(not any(x.is_symlink() for x in (p,*p.parents)),'aliased pinned path');return p
def frozen_name(path):
    p=Path(path);layout=frozen_layout()
    if any(p.is_relative_to(root) for root in layout.frozen_roots):return layout.logical(p)
    need(p.is_relative_to(ROOT),'path outside local or exact frozen files')
    name=str(p.relative_to(ROOT));need(frozen_path(name)==p,'physical/logical path mismatch');return name
def safe_path(root,name):
    p=_relative(name)
    if Path(root)==ROOT:return frozen_path(name)
    p=Path(root)/p;need(not any(x.is_symlink() for x in (p,*p.parents)),'aliased pinned path');return p
def _local_read(path,*,retain):
    p=Path(path)
    need(p.is_absolute() and p.resolve()==p and not any(x.is_symlink() for x in (p,*p.parents)),
         'regular unaliased file')
    h=hashlib.sha256();n=0;parts=[] if retain else None
    with os.fdopen(os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as f:
        before=os.fstat(f.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1,'regular single-link file')
        while b:=f.read(1048576):
            h.update(b);n+=len(b)
            if retain:parts.append(b)
        after=os.fstat(f.fileno())
    stamp=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_nlink)
    need(stamp(before)==stamp(after)==stamp(p.lstat()),'file changed during read')
    return (b''.join(parts) if retain else dict(bytes=n,sha256=h.hexdigest()))
def identity(p,*,reference_opened=False):
    p=Path(p);layout=frozen_layout()
    if any(p.is_relative_to(root) for root in layout.frozen_roots):
        return layout.identity(layout.logical(p),reference_opened=reference_opened)
    if p.is_relative_to(ROOT):
        name=str(p.relative_to(ROOT))
        need(not _frozen_namespace(name),'local frozen alias refused')
        need(Path(name).parts[0]!='work' or name==FROZEN_BINDING,'undeclared local work path: '+name)
    return _local_read(p,retain=False)
def checked(root,name,spec,*,reference_opened=False):
    p=safe_path(root,name);layout=frozen_layout()
    raw=(layout.read(name,reference_opened=reference_opened)
         if Path(root)==ROOT and layout.contains(name) else _local_read(p,retain=True))
    need(dict(bytes=len(raw),sha256=sha(raw))=={k:spec[k] for k in ('bytes','sha256')},
         'pinned file drift '+name);return raw
def stat_only(root,name,size):
    p=safe_path(root,name)
    if Path(root)==ROOT and frozen_layout().contains(name):frozen_layout().stat_reference(name)
    need(p.stat().st_size==size,'payload size')
def original():
    raw=(ROOT/'candidates/qwen2_fullblock_reference_m128/pins.json').read_bytes();need(sha(raw)==PINS_SHA256,'original pins');return parse(raw)
def artifact_binding():
    name='work/qwen2_recovered_inputs/ARTIFACTS.json';p=frozen_path(name)
    need(p.stat().st_size<=2*1024*1024,'bounded artifact binding');raw=frozen_layout().read(name)
    need(sha(raw)==digest(os.environ.get('QWEN2_FIXED93_ARTIFACTS_SHA256')),'explicit setup binding')
    b=parse(raw);fields(b,dict(schema=1,status='CURRENT_ARTIFACTS_INDEPENDENTLY_QUALIFIED',rows=128,old_pass_inherited=False),'current qualified artifacts');return b
# The original pure observation/layout verifier remains byte-pinned.
p=ROOT/'candidates/qwen2_fullblock_reference_m128/recipe.py';raw=p.read_bytes()
need(sha(raw)=='2548e4b447ac58580c0e941bdc5287f2fcbc9dea861bb2d0c601884e5dd2ff36','original pure recipe source')
O=types.ModuleType('_local_original_observation_contract');O.__file__=str(p);exec(compile(raw,str(p),'exec'),O.__dict__)
NAMES,TOKEN_MAJOR=O.NAMES,O.TOKEN_MAJOR
validate_observations=O.validate_observations

def load_pins(root=ROOT):
    need(root==ROOT,'fixed source root');b=artifact_binding();p=original()
    for n,s in p['producer_roles'].items():s['path']='work/qwen2_recovered_inputs/typed/'+n+'.bin'
    for s in p['raw_tensors']:s['path']='work/qwen2_recovered_inputs/raw/'+s['local_name']+'.bin'
    p['input_metadata']={'current_artifacts':dict(path='work/qwen2_recovered_inputs/ARTIFACTS.json',**identity(frozen_path('work/qwen2_recovered_inputs/ARTIFACTS.json')))}
    p['runtime_native_files']=b['runtime_native_files']
    p['sources']={}
    p['preserved_execution_closures']={}
    return p

def source_manifest(root=ROOT):
    from . import closure
    closure.source_manifest(root)
    return identity(closure.MANIFEST)
def source_check(root,pins):
    need(root==ROOT and same(pins,load_pins()),'current effective pins');source_manifest();return dict(status='CURRENT_LOCAL_SOURCE_BINDING_ONLY')
def metadata_check(root,pins):return dict(proof_files={})
def source_expectations(pins):
    raw=checked(ROOT,FROZEN_CONTRACT_FILE,dict(bytes=19978,sha256=FROZEN_CONTRACT_SHA256));f=parse(raw)
    validate_observations(f['outputs'],pins);return f['outputs'],dict(path=FROZEN_CONTRACT_FILE,bytes=len(raw),sha256=sha(raw))
def validate_bootstrap_metadata(pins=None,*,seal_sha256):
    # Compatibility API name only. This validates a CURRENT frozen pair, not bootstrap.
    pins=load_pins() if pins is None else pins;b=artifact_binding();directory=frozen_layout().reference_directory
    sealraw=frozen_layout().read(REFERENCE+'/SEAL.json');need(sha(sealraw)==digest(seal_sha256),'current reference seal')
    seal=parse(sealraw);fields(seal,dict(status='SEALED_FRESH_FROZEN_REPRODUCTION_REFERENCE_ONLY',mode='frozen',run_id='first',dut_executed=False,retries=0),'current frozen seal')
    expected,_=source_expectations(pins)
    files=set(METADATA_NAMES)|{n+'.f32le' for n in NAMES}|{'mask.bf16le'}
    need(set(seal['files'])==files and {p.name for p in directory.iterdir()}==files|{'SEAL.json'},'exact reference inventory')
    docs={}
    for n in METADATA_NAMES:
        spec=seal['files'][n];need(spec['bytes']<=262144,'bounded reference metadata')
        raw=checked(ROOT,REFERENCE+'/'+n,spec)
        if n.endswith('.json'):docs[n]=parse(raw)
    m=docs[REFERENCE_MANIFEST]
    fields(m,dict(stage='frozen',status='FRESH_OFFICIAL_AST_FULLBLOCK_CAPTURE_ONLY',frozen29_hash_matches=True,prior18_fresh_hash_matches=True,old_pass_inherited=False,dut_executed=False),'exact fresh reference flags')
    need(same(m['outputs'],expected),'all29 original targets')
    for n,s in expected.items():need(same(seal['files'][n+'.f32le'],{k:s[k] for k in ('bytes','sha256')}),'sealed payload target linkage')
    for n in files-set(METADATA_NAMES):stat_only(ROOT,REFERENCE+'/'+n,seal['files'][n]['bytes'])
    need(identity(directory/'SEAL.json')==b['reference_seal'],'reviewed reference seal')
    for n,s in b['reference_proofs'].items():checked(ROOT,n,s)
    return dict(status=STATUS,outputs=m['outputs'],manifest=m,seal=seal,bootstrap_seal=dict(path=REFERENCE+'/SEAL.json',**identity(directory/'SEAL.json')),bootstrap_manifest=dict(path=REFERENCE+'/'+REFERENCE_MANIFEST,**seal['files'][REFERENCE_MANIFEST]),bootstrap_status_preserved=False,fixed_expectations_match=True,old_pass_inherited=False,oracle_payload_read=False)

def require_frozen_references(pins,root=ROOT):
    need(root==ROOT,'fixed root');raw=(ROOT/FROZEN_BINDING).read_bytes();need(sha(raw)==digest(os.environ.get(BINDING_ENV)),'launch pinned oracle binding')
    b=parse(raw);fields(b,dict(schema=1,status=STATUS,old_pass_inherited=False,numerical_acceptance_claimed=False),'binding scope')
    from . import closure
    need(closure.digest(ROOT)==digest(os.environ.get(CLOSURE_ENV)), 'new reviewed manifest file identity')
    need(b['source_closure_sha256']==closure.map_digest(ROOT) and b['artifacts_sha256']==digest(os.environ.get('QWEN2_FIXED93_ARTIFACTS_SHA256')),'binding306-map/setup linkage; outer manifest is separately pinned')
    return validate_bootstrap_metadata(pins,seal_sha256=b['bootstrap_seal']['sha256'])
