"""Read-only provenance and narrow payload gate for an explicit M128 model run."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUTPUT_ROOT=ROOT/'work/qwen2_live_qkv_numeric_m128_20261014'
ROLES=frozenset(('x','gamma0','wq','wk','wv','bq','bk','bv','rope'))
OFFICIAL=frozenset(('n0','qr','q','kr','k','v'))
RAW=frozenset(('qraw','kraw','vraw'))


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for raw in iter(lambda:f.read(1<<20),b''):h.update(raw)
    return h.hexdigest()


def pins():return json.loads((HERE/'pins.json').read_text())


def verify_dependencies():
    p=pins()
    require(p['scope']=='M128_SOFTWARE_PC0_8_HELD' and type(p['rows']) is int and p['rows']==128,'model pin scope')
    for name,digest in p['dependency_sha256'].items():
        require(sha(ROOT/name)==digest,'model dependency drift: '+name)
    return p


def require_final_inputs():
    p=verify_dependencies()
    require(p.get('input_recipe_finalized') is True and
            isinstance(p.get('input_recipe_pins_sha256'),str) and
            re.fullmatch(r'[0-9a-f]{64}',p['input_recipe_pins_sha256']) is not None,
            'M128 input recipe/bootstrap not finalized; actual execution forbidden')
    return p


def sources():
    p=verify_dependencies()
    result=dict(p['dependency_sha256'])
    for f in HERE.iterdir():
        if f.is_file() and (f.suffix=='.py' or f.name in ('pins.json','source_correspondence.json')):
            result[str(f.relative_to(ROOT))]=sha(f)
    return result


def data_path(value):
    require(type(value) is str and bool(re.fullmatch(r'work/qwen2_live_qkv_inputs_m128/[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}',value)),
            'data must be an existing published input-recipe run directory')
    p=ROOT/value
    require(p.is_dir() and p.resolve()==p and not p.is_symlink(),'data directory missing or aliased')
    return p


def fresh_output(path,data):
    path=Path(path).absolute()
    require(path.resolve()==path and path.parent==OUTPUT_ROOT and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}',path.name),
            'output must be a fresh direct child of the numeric work directory')
    require(not path.exists() and not path.is_relative_to(data) and not data.is_relative_to(path),'output exists/overlaps inputs')


def input_recipe():
    model_pins=require_final_inputs()
    from candidates.qwen2_live_qkv_inputs_m128 import recipe
    require(recipe.PINS_SHA256==model_pins['input_recipe_pins_sha256'],'M128 final recipe identity differs')
    p=recipe.load_pins(ROOT)
    recipe.source_check(ROOT,p)
    recipe.require_frozen_references(p)
    return recipe,p


def validate_reference_metadata(data,ready,subset_sha,inputs_sha):
    R,p=input_recipe()
    relative=str(data.relative_to(ROOT))
    # The input recipe owns the M128-only schema, strict runtime/source
    # provenance and frozen logical/token-major hashes. This helper does not
    # open f32 payloads, so it is usable before the actual producer seal.
    return R.verify_reference_metadata(ROOT,p,relative+'/raw',relative+'/inputs',
        relative+'/reference',subset_sha,inputs_sha)


def validate_inputs(data):
    R,p=input_recipe();relative=str(data.relative_to(ROOT))
    _,raw,subset_sha,_=R.read_subset(ROOT,p,relative+'/raw')
    ready,inputs_sha,directory=R.read_inputs(ROOT,p,relative+'/inputs',relative+'/raw',subset_sha)
    inputs=R.check_records(directory,ready['roles'],p['roles'],'.bin')
    require(set(inputs)==ROLES,'exact nine executable roles required')
    validate_reference_metadata(data,ready,subset_sha,inputs_sha)
    evidence={str(f.relative_to(ROOT)):sha(f) for f in
        (data/'raw/subset_manifest.json',data/'inputs/INPUTS_READY.json',data/'reference/REFERENCE.json')}
    # Hash the checked eight BF16 tensor bytes, never prelaunch intermediates.
    raw_identity={n:dict(bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for n,v in raw.items()}
    return inputs,ready,evidence,dict(raw_tensors=raw_identity,input_roles=9,official_reference_nodes_metadata=9,
        reference_payloads_read_before_seal=0,recipe_sha256=R.recipe_identity(ROOT),
        source_pin_sha256=R.PINS_SHA256,full_checkpoint_sha256_verified=False)


def raw_identity(data):
    R,p=input_recipe()
    _,raw,_,_=R.read_subset(ROOT,p,str(data.relative_to(ROOT))+'/raw')
    return {n:dict(bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for n,v in raw.items()}


def validate_references(data,ready):
    R,p=input_recipe()
    subset_sha=sha(data/'raw/subset_manifest.json');inputs_sha=sha(data/'inputs/INPUTS_READY.json')
    ref=validate_reference_metadata(data,ready,subset_sha,inputs_sha)
    values=R.check_records(data/'reference',ref['outputs'],p['references'],'.f32le')
    require(R.compare_reference(values,p)==ref['reference_hash_comparison'],'official layout provenance drift')
    return ref,values


def correspondence():
    return json.loads((HERE/'source_correspondence.json').read_text())


def official_pass(comparisons):
    require(set(comparisons)==OFFICIAL|RAW,'exact nine producer comparisons required')
    require(all(type(comparisons[n]['official_numeric_pass']) is bool for n in OFFICIAL),
            'all six official producer comparisons are mandatory')
    require(all(comparisons[n]['official_numeric_pass'] is None for n in RAW),'no invented official raw acceptance')
    return all(comparisons[n]['official_numeric_pass'] for n in OFFICIAL)


class OracleGate:
    def __init__(self,data,out):
        self.data,self.out=Path(data),Path(out)
        self.opened=False;self.blocked=0;self.reference_reads=[]
        self.provenance_reads=[]
        self.raw_names=set(pins()['raw_files'])
        # This is a pinned JSON safetensors header, not tensor bytes. The
        # published recipe rechecks it as source metadata before/after use.
        self.header=ROOT/'config/upstream/weight_headers/qwen2_1p5b/model.safetensors.header.bin'
        require(str(self.header.relative_to(ROOT)) in pins()['dependency_sha256'],'header metadata is not source-pinned')

    def audit(self,event,args):
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        name=args[0].decode() if isinstance(args[0],bytes) else args[0]
        p=Path(name).resolve()
        if p.suffix not in ('.bin','.f32le','.npy','.npz'):return
        if p==self.header:return
        if p.is_relative_to(self.out):return
        allowed=(p.parent==self.data/'inputs' and p.name in {n+'.bin' for n in ROLES})
        reference=p.parent==self.data/'reference' and p.name in {n+'.f32le' for n in ('x','n0','qr','q','kr','k','v','cos','sin')}
        if reference and self.opened:
            self.reference_reads.append(str(p.relative_to(self.data)));return
        if self.opened and p.parent==self.data/'raw' and p.name in self.raw_names:
            self.provenance_reads.append(str(p.relative_to(self.data)));return
        if not allowed:
            self.blocked+=1
            raise ValueError('unapproved payload/reference before actual output seal: '+str(p))
