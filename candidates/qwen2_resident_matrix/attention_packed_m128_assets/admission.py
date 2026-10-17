"""Separate strict M128 admission using immutable genuine original assets.

No model, reference producer, native kernel or Public numerical job is executed.
Source and admission receipts grant no launch authority.
"""
import os
from pathlib import Path
from . import origin as O, prerequisite, views
R=O.R
PROFILE=O.PROFILE
STATUS='SEALED_PACKED_M128_REUSED_INPUTS_NOT_EXECUTED'

def exact(value,keys,label):R.need(type(value) is dict and set(value)==set(keys),label)
def absolute(value):
 R.need(type(value) is str and value and '\\' not in value and '\x00' not in value and
  Path(value).is_absolute() and '..' not in Path(value).parts and str(Path(value))==value,
  'canonical absolute origin path')
def pointer(value):
 exact(value,('path','sha256'),'exact metadata pointer');absolute(value['path'])
 R.need(R.digest(value['sha256']),'metadata pointer digest')
def validate_manifest(value,*,rows=128):
 exact(value,('schema','profile','status','rows','past_tokens','enable_raw_kv','enable_packed',
  'source_sha256','source_manifest_sha256','origin','origin_manifest','m16_prerequisite','library'), 'M128 linked manifest schema')
 R.need(type(rows) is int and rows==128 and type(value['schema']) is int and value['schema']==1 and
  value['profile']==PROFILE and value['status']==STATUS and type(value['rows']) is int and value['rows']==128 and
  type(value['past_tokens']) is int and value['past_tokens']==0 and value['enable_raw_kv'] is True and
  value['enable_packed'] is True, 'canonical separate M128/past-zero profile')
 sources=value['source_sha256']
 R.need(type(sources) is dict and sources and all(type(k) is str and k and '\\' not in k and '\x00' not in k and
  not Path(k).is_absolute() and all(p not in ('','.','..') for p in k.split('/')) and R.digest(v) for k,v in sources.items()),
  'M128 source map schema')
 R.need(R.digest(value['source_manifest_sha256']) and R.sha(R.encoded(sources))==value['source_manifest_sha256'], 'M128 source map digest')
 for key in ('origin','m16_prerequisite'):absolute(value[key])
 pointer(value['origin_manifest'])
 R.need(value['origin_manifest']['path']==str(Path(value['origin'])/'private/assets/ASSETS.json'), 'original M128 receipt path cannot be remapped')
 exact(value['library'],('receipt','origin_root','sha256'),'strict packed library schema')
 pointer(value['library']['receipt']);absolute(value['library']['origin_root'])
 R.need(R.digest(value['library']['sha256']), 'packed library digest')
 return value

def read_manifest(path,expected_sha256,*,rows=128):
 p=R.safe_path(path)
 with p.open('rb') as f:raw=f.read(R.MAX_JSON+1)
 R.need(R.digest(expected_sha256) and len(raw)<=R.MAX_JSON and R.sha(raw)==expected_sha256, 'M128 manifest bytes')
 return validate_manifest(R.strict_json(raw),rows=rows)

def source_snapshot(*,enable_raw_kv=False):
 R.need(enable_raw_kv is True,'M128 linked profile requires explicit raw KV')
 from ..attention_packed_m128_entry import contract
 return contract.snapshot()
def own_sources():return source_snapshot(enable_raw_kv=True)
def fresh_mode(enabled,manifest=None,manifest_sha256=None,*,rows=None):
 R.need(enabled is True and manifest is not None and R.digest(manifest_sha256) and
  (rows is None or type(rows) is int and rows==128),'explicit separate linked M128 profile')
 return True
def snapshot_mode(snapshot,enabled,*,enable_raw_kv=False):
 R.need(enabled is True and enable_raw_kv is True and snapshot.get('fresh_profile') is True,'M128 snapshot modes')
 identity=snapshot.get('fresh_assets');exact(identity,('profile','manifest','manifest_sha256','enable_raw_kv'),'M128 snapshot identity')
 R.need(identity['profile']==PROFILE and identity['enable_raw_kv'] is True,'M128 snapshot profile')
 fresh_mode(True,identity['manifest'],identity['manifest_sha256'],rows=snapshot['rows']);return identity

read_reference_bytes=views.read_reference_bytes
read_native_reference=views.read_native_reference

def verify_library(receipt,*,manifest):
 from ..attention_packed_m128_entry import contract
 from ..attention_packed_m16_entry import library_origin
 sources=contract.snapshot();pins=O.provenance()['library'];lib=manifest['library']
 R.need(lib['receipt']['sha256']==pins['receipt_sha256'] and lib['sha256']==pins['sha256'], 'exact qualified combined packed library required')
 verifier='candidates/qwen2_resident_matrix/attention_packed_m16_entry/library_origin.py'
 R.need(Path(library_origin.__file__).resolve()==contract.ROOT/verifier and
  sources.get(verifier)==R.file_hash(contract.ROOT/verifier), 'unchanged strict verifier import origin')
 R.need(str(R.safe_path(receipt))==str(R.safe_path(lib['receipt']['path'])),'exact packed compile receipt path')
 built=library_origin.verify(receipt,lib['receipt']['sha256'],origin_root=lib['origin_root'],
  execution_root=contract.ROOT,library_sha256=lib['sha256'])
 R.need(contract.snapshot()==sources,'source changed during strict library verification')
 return built

def verify_current_backend(origin):
 """Read current source/build identity only. Runner configures thread policy."""
 from ..raw_kv_public_fresh import setup
 from ..attention_packed_m128_entry import contract
 sources=contract.snapshot();name='candidates/qwen2_resident_matrix/raw_kv_public_fresh/setup.py'
 R.need(Path(setup.__file__).resolve()==contract.ROOT/name and sources.get(name)==R.file_hash(contract.ROOT/name), 'current backend verifier import source')
 pins=O.provenance();expected=R.read_metadata(origin,'private/assets/backend.json',pins['metadata']['private/assets/backend.json'])
 torch,identity=setup.backend_identity();setup.backend_threads(torch)
 R.need(R.same(R.strict_json(R.encoded(identity)),expected['identity']), 'current backend/source/build differs from original M128')
 R.need(all(os.environ.get(k)=='4' for k in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS')), 'original M128 BLAS environment required')
 return dict(current_backend_verified=True,native_forward_executed=False)

def verify(path,expected_sha256,*,rows=128,enable_raw_kv=False):
 R.need(type(rows) is int and rows==128 and enable_raw_kv is True,'explicit linked M128/raw admission')
 from ..attention_packed_m128_entry import contract
 sources=contract.snapshot();contract.git_context()
 manifest=read_manifest(path,expected_sha256,rows=rows)
 R.need(R.same(manifest['source_sha256'],sources),'manifest/executing M128 source identity')
 pins=O.provenance()
 R.need(manifest['origin_manifest']['sha256']==pins['metadata']['private/assets/ASSETS.json']['sha256'], 'authentic original M128 receipt required')
 before,assets,native,exports=O.snapshot(manifest['origin'],content=True)
 m16=prerequisite.verify(manifest['m16_prerequisite'],sources)
 verify_current_backend(manifest['origin']);built=verify_library(manifest['library']['receipt']['path'],manifest=manifest)
 admitted=views.build_views(manifest_path=R.safe_path(path),manifest_sha256=expected_sha256,
  origin_assets=Path(manifest['origin'])/'private/assets',origin_manifest=assets,native_result=native,
  exported=exports,library_receipt=manifest['library']['receipt']['path'],library=built['library'],
  origin_identity=before,m16_prerequisite=m16)
 after,_,_,_=O.snapshot(manifest['origin'],content=True)
 R.need(R.same(after,before) and R.same(prerequisite.verify(manifest['m16_prerequisite'],sources),m16), 'original assets or repaired M16 evidence changed during admission')
 R.need(contract.snapshot()==sources and R.same(read_manifest(path,expected_sha256,rows=rows),manifest), 'M128 source/manifest postflight drift')
 verify_library(manifest['library']['receipt']['path'],manifest=manifest)
 admitted['provenance']['origin_before_after_unchanged']=True
 return admitted

def seal_manifest(destination,*,origin,compile_receipt,compile_origin,m16_prerequisite):
 """Seal a NEW private adapter receipt; no historical files are altered."""
 from ..attention_packed_m128_entry import contract
 sources=contract.snapshot();pins=O.provenance()
 origin=R.safe_path(origin,directory=True);compiled=R.safe_path(compile_receipt)
 compile_origin=R.safe_path(compile_origin,directory=True);m16_prerequisite=R.safe_path(m16_prerequisite,directory=True)
 destination=Path(destination).absolute();absolute(str(destination))
 R.need(not destination.exists() and not destination.is_symlink(),'fresh M128 adapter manifest required')
 R.safe_path(destination.parent,directory=True)
 R.need(not any(destination.is_relative_to(p) for p in (origin,m16_prerequisite,compile_origin,compiled.parent)), 'adapter receipt must stay outside immutable origins')
 value=dict(schema=1,profile=PROFILE,status=STATUS,rows=128,past_tokens=0,enable_raw_kv=True,enable_packed=True,
  source_sha256=sources,source_manifest_sha256=R.sha(R.encoded(sources)),origin=str(origin),
  origin_manifest=dict(path=str(origin/'private/assets/ASSETS.json'),sha256=pins['metadata']['private/assets/ASSETS.json']['sha256']),
  m16_prerequisite=str(m16_prerequisite),library=dict(receipt=dict(path=str(compiled),sha256=pins['library']['receipt_sha256']), origin_root=str(compile_origin),sha256=pins['library']['sha256']))
 validate_manifest(value);raw=R.encoded(value);digest=R.sha(raw)
 with destination.open('xb') as stream:stream.write(raw)
 try:admitted=verify(destination,digest,rows=128,enable_raw_kv=True)
 except BaseException:
  destination.unlink(missing_ok=True);raise
 return destination,digest,admitted
