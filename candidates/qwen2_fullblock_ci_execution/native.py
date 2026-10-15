"""Fresh CI native build, with independently supplied receipt digest at load.

Compilation is a new compiler/ELF observation, never historical native identity.
No tensor arithmetic is executed by this adapter. Full execution needs separate
source/reference/platform approval; a successful build grants no numerical GO.
"""
from pathlib import Path
import hashlib
import re
from . import inputs
ROOT=Path(__file__).resolve().parents[2]
DIRECTORY='work/qwen2_fullblock_ci_native/ci01'
SOURCE_HASHES={'candidates/qwen2_resident_matrix/official_bf16/dense_silu.py': 'dfd44e15f274090ba7d1eca4fa6c59248e11029dad3c5fcfc0b45693c6267699', 'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp': '7702e5975ff04393deb4969835eb5ffcfbb99258329ee6ac27fd75b289356e14', 'candidates/qwen2_resident_matrix/official_bf16/silu_recipe.cpp': 'd319d3431316b4ff0f299beac5931f718a6a3a446e8de06398b172ebb6e0401c', 'candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp': 'bdd7513bd788c03ac92be1d7c2f3553d3d7e0723ce1ac2892e93dcef58782ef1', 'candidates/qwen2_resident_matrix/ffn_tiles/silu_recipe.cpp': '3195c9f9d4136e81d271090632489def292257e8323bd6ef4ef75f78cbdaf067'}

def need(ok,message):
    if not ok:raise ValueError(message)

def sources(root):
    result={}
    for name,digest in SOURCE_HASHES.items():
        path=inputs.safe_path(root,name)
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        need(actual==digest,'native arithmetic source drift: '+name)
        result[name]=actual
    return result

def location(root):
    root=Path(root)
    need(root==ROOT==inputs.CI_ROOT and root.resolve()==root,'fixed CI native root')
    need(not any(p.is_symlink() for p in (root,*root.parents)),'native root alias')
    return inputs.safe_path(root,DIRECTORY)

def build(root=ROOT,*,execute=False):
    if not execute:return dict(status='NOT_EXECUTED',numeric_execution_allowed=False)
    out=location(root)
    need(not out.exists(),'native build must be fresh')
    before=sources(root)
    from candidates.qwen2_resident_matrix.official_bf16 import dense_silu as dense
    _,receipt=dense.build_library(out)
    need(sources(root)==before,'native source changed during build')
    record=out/'official_bf16_compile.json'
    checked=dense.verify_library(record)
    need(checked==receipt,'fresh compile record mismatch')
    return dict(status='FRESH_NATIVE_BUILT_ONLY',receipt_sha256=hashlib.sha256(record.read_bytes()).hexdigest(),
        library_sha256=receipt['library_sha256'],numeric_execution_allowed=False)

def load(*,receipt_sha256,root=ROOT):
    need(type(receipt_sha256) is str and re.fullmatch('[0-9a-f]{64}',receipt_sha256),
         'independently bound receipt digest required')
    out=location(root)
    before=sources(root)
    path=inputs.safe_path(root,DIRECTORY+'/official_bf16_compile.json')
    raw=path.read_bytes()
    need(hashlib.sha256(raw).hexdigest()==receipt_sha256,'native receipt drift')
    from candidates.qwen2_resident_matrix.official_bf16 import dense_silu as dense
    receipt=dense.verify_library(path)
    library=inputs.safe_path(root,DIRECTORY+'/official_bf16_matrix_silu.so')
    need(receipt['library']==str(library),'native library outside fixed build')
    module=dense.configure_silu_library(dense.configure_library(dense.C.CDLL(str(library))))
    need(path.read_bytes()==raw and sources(root)==before,'native boundary changed during load')
    dense.verify_library(path)
    return module,receipt
