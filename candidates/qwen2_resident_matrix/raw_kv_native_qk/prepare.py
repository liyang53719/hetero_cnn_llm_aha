"""Exact two-patch preparation, leaving original and QKV-only paths frozen."""
import ast
import hashlib
from pathlib import Path
import subprocess
from ..raw_kv_native_qkv import prepare as prior

ROOT=Path(__file__).resolve().parents[3]
PREFIX='candidates/qwen2_resident_matrix/raw_kv_native_qk/'
ORIGINAL=prior.ORIGINAL
PROFILE='qwen2-independent-qkv-and-qk-pair-v1'
OLD_PINS='396b82924894b14c22a9647537159f73fc497a53805f2f0c85510c01410fbb7a'


def need(ok):
    if not ok:raise ValueError('independent QK source contract')


def snapshot():
    from . import kernel
    frozen=kernel.source_snapshot()
    need(prior.snapshot()['pins_sha256']==OLD_PINS)
    return frozen


def check_scope(base,generated):
    """Disabled AST projection only; enabled branch separately pinned/reviewed."""
    before,after=ast.parse(base),ast.parse(generated)
    funcs={n.name:n for n in after.body if isinstance(n,ast.FunctionDef)}
    independent=funcs['independent_forward']
    index=next(i for i,n in enumerate(independent.body) if isinstance(n,ast.If) and
               ast.unparse(n.test)=="mode == 'bf16' and qkv_recipe is not None")
    branch=independent.body[index]
    need(len(branch.body)==1 and len(branch.orelse)==1 and
         ast.unparse(branch.body[0])=='qk_dot = qkv_recipe.qk_dot(q, repeated_k)' and
         ast.unparse(branch.orelse[0])=='qk_dot = np.matmul(q, repeated_k.swapaxes(-1, -2), dtype=np.float32)')
    independent.body.pop(index)
    assignment=independent.body[index]
    need(ast.unparse(assignment)=="scores = keep('scores', round_output(round_output(qk_dot) / math.sqrt(dim)))")
    oldfunc=next(n for n in before.body if isinstance(n,ast.FunctionDef) and n.name=='independent_forward')
    oldassignment=next(n for n in oldfunc.body if isinstance(n,ast.Assign) and
                       any(isinstance(t,ast.Name) and t.id=='scores' for t in n.targets))
    independent.body[index]=oldassignment
    imports=[n for n in ast.walk(after) if isinstance(n,ast.ImportFrom) and
             n.module=='candidates.qwen2_resident_matrix.raw_kv_native_qk.adapter']
    need(len(imports)==2)
    for node in imports:node.module='candidates.qwen2_resident_matrix.raw_kv_native_qkv.adapter'
    need(ast.dump(before)==ast.dump(after))


def prepare(out):
    frozen=snapshot()
    result=prior.prepare(out)
    target=Path(out)/ORIGINAL
    base=target.read_bytes()
    need(hashlib.sha256(base).hexdigest()==result['generated_module_sha256'])
    subprocess.run(['patch','--batch','--fuzz=0','-p1'],cwd=out,
                   input=prior.read(PREFIX+'variant.patch'),check=True,capture_output=True,timeout=10)
    generated=target.read_bytes()
    need(hashlib.sha256(generated).hexdigest()==frozen['generated_module_sha256'])
    check_scope(base,generated)
    need(snapshot()==frozen)
    return dict(status='PASS_SOURCE_PREPARATION_ONLY',profile=PROFILE,**frozen,numerical_execution=False)
