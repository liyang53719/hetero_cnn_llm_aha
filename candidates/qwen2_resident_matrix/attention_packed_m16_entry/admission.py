"""Linked M16 asset checks. No historical manifest is relabeled or overwritten.

This validates the exact successful fresh preparation and explicit reused
references. Full execution is selected separately by the reviewed M16 runner.
"""
from pathlib import Path
from ..attention_packed_m16_assets import reuse as R
from ..raw_kv_public_fresh import assets as old
from . import views,library_origin
PROFILE=views.PROFILE
STATUS='SEALED_PACKED_M16_INPUTS_NOT_EXECUTED'

def exact(value,keys,label):R.need(type(value) is dict and set(value)==set(keys),label)
def pointer(value):
 exact(value,('path','sha256'),'exact metadata pointer')
 R.need(type(value['path']) is str and Path(value['path']).is_absolute() and '..' not in Path(value['path']).parts and R.digest(value['sha256']),'metadata pointer types')

def validate_manifest(value,*,rows=16):
 exact(value,('schema','profile','status','rows','past_tokens','enable_raw_kv','enable_packed',
  'source_sha256','source_manifest_sha256','origin','references','preparation_launch','preparation_summary','supervisor','library'),'linked manifest schema')
 R.need(type(rows) is int and rows==16 and type(value['schema']) is int and value['schema']==1 and
  value['profile']==PROFILE and value['status']==STATUS and type(value['rows']) is int and value['rows']==16 and
  type(value['past_tokens']) is int and value['past_tokens']==0 and value['enable_raw_kv'] is True and
  value['enable_packed'] is True,'canonical linked M16 profile')
 sources=value['source_sha256']
 R.need(type(sources) is dict and sources and all(type(k) is str and k and '\\' not in k and
  not Path(k).is_absolute() and all(p not in ('','.','..') for p in k.split('/')) and R.digest(v) for k,v in sources.items()),'source map schema')
 R.need(R.digest(value['source_manifest_sha256']) and R.sha(R.encoded(sources))==value['source_manifest_sha256'],'source map digest')
 R.need(type(value['origin']) is str and Path(value['origin']).is_absolute() and '..' not in Path(value['origin']).parts,'explicit origin root')
 for key in ('references','preparation_launch','preparation_summary','supervisor'):pointer(value[key])
 exact(value['library'],('receipt','origin_root','sha256'),'library origin schema');pointer(value['library']['receipt'])
 R.need(type(value['library']['origin_root']) is str and Path(value['library']['origin_root']).is_absolute() and
  '..' not in Path(value['library']['origin_root']).parts and R.digest(value['library']['sha256']),'library origin types')
 return value

def read_manifest(path,expected_sha256,*,rows=16):
 p=R.safe_path(path)
 with p.open('rb') as f:raw=f.read(R.MAX_JSON+1)
 R.need(R.digest(expected_sha256) and len(raw)<=R.MAX_JSON and R.sha(raw)==expected_sha256,'linked manifest bytes')
 return validate_manifest(R.strict_json(raw),rows=rows)

def source_snapshot(*,enable_raw_kv=False):
 R.need(enable_raw_kv is True,'linked profile requires explicit raw KV')
 from . import contract
 return contract.snapshot()
def own_sources():return source_snapshot(enable_raw_kv=True)
def fresh_mode(enabled,manifest=None,manifest_sha256=None,*,rows=None):
 R.need(enabled is True and manifest is not None and R.digest(manifest_sha256) and
  (rows is None or type(rows) is int and rows==16),'explicit linked fresh M16 profile')
 return True
def snapshot_mode(snapshot,enabled,*,enable_raw_kv=False):
 R.need(enabled is True and enable_raw_kv is True and snapshot.get('fresh_profile') is True,'linked snapshot modes')
 identity=snapshot.get('fresh_assets');exact(identity,('profile','manifest','manifest_sha256','enable_raw_kv'),'linked snapshot identity')
 R.need(identity['profile']==PROFILE and identity['enable_raw_kv'] is True,'linked snapshot profile')
 fresh_mode(True,identity['manifest'],identity['manifest_sha256'],rows=snapshot['rows'])
 return identity

# Preserve original late comparison API; callers still use the original
# reference_gate and may open these only after acknowledged whole terminal.
read_reference_bytes=views.read_reference_bytes
read_native_reference=views.read_native_reference

def verify_library(receipt,*,manifest):
 lib=manifest['library']
 R.need(str(R.safe_path(receipt))==str(R.safe_path(lib['receipt']['path'])),'exact linked compile receipt')
 from . import contract
 return library_origin.verify(receipt,lib['receipt']['sha256'],origin_root=lib['origin_root'],
  execution_root=contract.ROOT,library_sha256=lib['sha256'])

def verify_current_backend(origin):
 # Configure threads once in the separately bounded runner, not while repeated
 # admission/snapshot validation is in progress. No reference forward is run.
 from ..raw_kv_public_fresh import setup
 from . import contract
 contract.snapshot()
 R.need(Path(setup.__file__).resolve()==contract.ROOT/'candidates/qwen2_resident_matrix/raw_kv_public_fresh/setup.py',
  'exact backend verifier import path')
 pins=R.contract()
 expected=R.read_metadata(origin,'private/assets/backend.json',pins['metadata']['private/assets/backend.json'])
 torch,identity=setup.backend_identity();setup.backend_threads(torch)
 R.need(R.same(R.strict_json(R.encoded(identity)),expected['identity']),'current backend/source/build differs from retained references')
 return dict(current_backend_verified=True,native_forward_executed=False)

def verify(path,expected_sha256,*,rows=16,enable_raw_kv=False):
 R.need(type(rows) is int and rows==16 and enable_raw_kv is True,'explicit linked M16/raw admission')
 from . import contract,preparation_receipts
 sources=contract.snapshot();contract.git_context()
 manifest=read_manifest(path,expected_sha256,rows=rows)
 R.need(R.same(manifest['source_sha256'],sources),'manifest/executing source identity')
 fresh_root,references=preparation_receipts.verify(manifest)
 origin=R.safe_path(manifest['origin'],directory=True);pins=R.contract()
 origin_manifest=R.read_metadata(origin,'private/assets/ASSETS.json',pins['metadata']['private/assets/ASSETS.json'])
 native=R.read_metadata(origin,'private/assets/native_m16/RESULT.json',pins['metadata']['private/assets/native_m16/RESULT.json'])
 R.validate_native(native,origin_manifest['native_m16'],origin_manifest['payload']['manifest']['sha256'])
 verify_current_backend(origin)
 built=verify_library(manifest['library']['receipt']['path'],manifest=manifest)
 export_path=R.checked(fresh_root,references['producers']['sequential']['export_receipt'],content=True)
 exported=R.strict_json(export_path.read_bytes())
 admitted=views.build_views(manifest_path=R.safe_path(path),manifest_sha256=expected_sha256,
  origin_assets=origin/'private/assets',fresh_root=fresh_root,origin_manifest=origin_manifest,
  references=references,native_result=native,exported=exported,
  library_receipt=manifest['library']['receipt']['path'],library=built['library'])
 R.need(contract.snapshot()==sources and R.same(read_manifest(path,expected_sha256,rows=rows),manifest),
  'postflight linked source/manifest drift')
 return admitted

def seal_manifest(destination,*,origin,preparation_workspace,compile_receipt,compile_origin):
 """Create a fresh private manifest only after all authentic artifacts validate.

 The caller owns the single external deadline and configures the original
 thread/determinism policy first. This function performs no numerical job.
 """
 from . import contract,preparation_receipts
 sources=contract.snapshot();pins=preparation_receipts.provenance()
 origin=R.safe_path(origin,directory=True);work=R.safe_path(preparation_workspace,directory=True)
 compiled=R.safe_path(compile_receipt);compile_origin=R.safe_path(compile_origin,directory=True)
 destination=Path(destination).absolute()
 R.need('..' not in destination.parts and not destination.exists() and not destination.is_symlink(),'fresh private manifest required')
 R.safe_path(destination.parent,directory=True)
 def ref(path,key):return dict(path=str(path),sha256=pins[key])
 value=dict(schema=1,profile=PROFILE,status=STATUS,rows=16,past_tokens=0,enable_raw_kv=True,enable_packed=True,
  source_sha256=sources,source_manifest_sha256=R.sha(R.encoded(sources)),origin=str(origin),
  references=ref(work/'references/M16_REFERENCES.json','references_sha256'),
  preparation_launch=ref(work/'LAUNCH_RECEIPT.json','launch_receipt_sha256'),
  preparation_summary=ref(work/'summary.json','preparation_summary_sha256'),
  supervisor=ref(work/'SUPERVISOR.json','supervisor_sha256'),
  library=dict(receipt=ref(compiled,'compile_receipt_sha256'),origin_root=str(compile_origin),sha256=pins['library_sha256']))
 validate_manifest(value)
 raw=R.encoded(value);digest=R.sha(raw)
 with destination.open('xb') as stream:stream.write(raw)
 try:
  admitted=verify(destination,digest,rows=16,enable_raw_kv=True)
 except BaseException:
  destination.unlink(missing_ok=True)
  raise
 return destination,digest,admitted
