"""Explicit immutable-origin strict ELF verifier for the linked M16 profile.

The original compile receipt is never rewritten. Its argv must still name its
actual build tree; the four arithmetic bytes must also equal the executing tree.
This verifies files/tool identity only and never opens an ELF with CDLL.
"""
import hashlib,json,types
from pathlib import Path

LIMIT=262144

def need(value,message):
 if not value:raise ValueError(message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def safe(path,*,directory=False):
 p=Path(path)
 need(p.is_absolute() and '..' not in p.parts,'absolute origin path required')
 current=Path(p.anchor)
 for part in p.parts[1:]:
  current=current/part;need(not current.is_symlink(),'origin symlink prohibited')
 need(p.is_dir() if directory else p.is_file(),'origin path type')
 return p.resolve(strict=True)
def metadata(path,expected):
 p=safe(path)
 need(type(expected) is str and len(expected)==64 and all(c in '0123456789abcdef' for c in expected),'receipt SHA256')
 with p.open('rb') as f:raw=f.read(LIMIT+1)
 need(len(raw)<=LIMIT and hashlib.sha256(raw).hexdigest()==expected,'origin receipt bytes')
 def pairs(items):
  out={}
  for k,v in items:need(k not in out,'duplicate receipt key');out[k]=v
  return out
 value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('finite receipt JSON required')))
 need(type(value) is dict,'receipt object')
 return p,value

def loaded_original(execution_root):
 from ..official_bf16 import dense_silu as original
 file=safe(Path(execution_root)/'candidates/qwen2_resident_matrix/official_bf16/dense_silu.py')
 need(Path(original.__file__).resolve()==file,'strict verifier imported from wrong tree')
 code=compile(file.read_bytes(),str(file),'exec',dont_inherit=True)
 definitions={x.co_name:x for x in code.co_consts if isinstance(x,types.CodeType)}
 for name in ('_sha','compiler_identity','verify_library'):
  function=getattr(original,name,None)
  need(type(function) is types.FunctionType and function.__module__==original.__name__ and
       function.__code__.co_filename==str(file) and function.__code__==definitions[name],'strict verifier loaded method drift')
 return original

def verify(receipt,receipt_sha256,*,origin_root,execution_root,library_sha256):
 original=loaded_original(execution_root)
 path,data=metadata(receipt,receipt_sha256)
 origin=safe(origin_root,directory=True);execution=safe(execution_root,directory=True)
 need(type(data.get('schema')) is int and data['schema']==1 and
      type(data.get('returncode')) is int and data['returncode']==0 and
      data.get('policy')==original.POLICY_VERSION and data.get('status')=='PASS' and
      data.get('selected_silu_entrypoint')=='sf_vector_bf16_v1' and
      data.get('original_silu_entrypoint')=='sf_vector','original strict receipt policy')
 binary=safe(data['library'])
 need(type(library_sha256) is str and data['library_sha256']==library_sha256 and
      sha(binary)==library_sha256,'origin ELF identity')
 with binary.open('rb') as f:need(f.read(4)==b'\x7fELF','origin ELF format')
 compiler=original.compiler_identity()
 need(data['compiler']==compiler,'current compiler differs from origin')
 expected=[compiler['path'],*original.STRICT_FLAGS,*(str(origin/n) for n in original.TRANSLATION_UNITS),'-o',str(binary)]
 need(data['argv']==expected,'origin strict argv/source paths')
 old={n:sha(safe(origin/n)) for n in original.SOURCE_CLOSURE}
 current={n:sha(safe(execution/n)) for n in original.SOURCE_CLOSURE}
 need(data['source_sha256']==old==current,'origin/execution arithmetic closure differs')
 # Pin the unchanged original verifier implementation too: executing a new
 # helper with matching C++ alone is not an admissible source substitution.
 verifier='candidates/qwen2_resident_matrix/official_bf16/dense_silu.py'
 need(sha(safe(origin/verifier))==sha(safe(execution/verifier)),'strict verifier source differs')
 need(sha(path)==receipt_sha256,'origin receipt changed during validation')
 return data
