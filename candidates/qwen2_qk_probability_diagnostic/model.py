"""Cold-by-default binding and exact AST extraction for arithmetic diagnostics."""
import ast
import ctypes
import hashlib
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OWNER=ROOT/'candidates/qwen2_resident_matrix/official_bf16/owners.py'
NATIVE=ROOT/'work/native_recovery_20261015/build01/official_bf16_matrix_silu.so'
NATIVE_SHA='a44f4cd7861d1207698bb3dfc89820ded30a44db1cf1c8b9f951019d1edce1fa'
OWNER_SHA='0256c3ad3a90874bb032e39b5bdf28014a05f4ab08960c5bcf952cd5fdd5d05a'

def need(ok,why):
    if not ok:raise ValueError(why)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def owner_nodes():
    need(sha(OWNER)==OWNER_SHA,'current official owner changed')
    tree=ast.parse(OWNER.read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='OfficialAttentionOwner')
    fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_attention')
    head=fn.body[0].body[0]
    key=next(n for n in head.body if isinstance(n,ast.For) and ast.unparse(n.target)=='key')
    start=next(i for i,n in enumerate(key.body) if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='total')
    end=next(i for i,n in enumerate(key.body) if isinstance(n,ast.Expr) and ast.unparse(n.value).startswith('scores.append'))
    qk=key.body[start:end]
    start=next(i for i,n in enumerate(head.body) if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='(probabilities, total)')
    end=next(i for i,n in enumerate(head.body) if isinstance(n,ast.For) and ast.unparse(n.target)=='col')
    soft=head.body[start:end]
    col=head.body[end]
    inner=col.body[0]
    normalize=inner.body[0]
    need(ast.unparse(qk[-1])=="score = self._op('bf', self._op('mul', dot, 1035273459))",'QK boundary changed')
    return qk,soft,normalize

def exact_owner_functions():
    """Compile unchanged original owner arithmetic statements, no approximation.

    The caller supplies the existing ScalarService. Memory and Matrix protocol
    are outside this isolated arithmetic check. Normalization is copied from
    the original first PV-column iteration; every source statement is retained.
    """
    from candidates.qwen2_resident_matrix.ffn_attention.scalar_recipe import exp_negative
    qk,soft,normalize=owner_nodes()
    def make(name,args,body,tail):
        fn=ast.parse('def '+name+'('+args+'):\n    pass').body[0]
        fn.body=body+ast.parse(tail).body
        return fn
    qfn=make('qk','self, lanes',qk,'return total, dot, score')
    sfn=make('soft','self, scores, maximum',soft,
        'result = []\nfor key, probability in enumerate(probabilities):\n    pass\nreturn result, probabilities, total, inverse')
    sfn.body[-2].body=[normalize,ast.parse('result.append(probability)').body[0]]
    module=ast.fix_missing_locations(ast.Module(body=[qfn,sfn],type_ignores=[]))
    ns={'exp_negative':exp_negative};exec(compile(module,str(OWNER),'exec'),ns)
    return ns['qk'],ns['soft']

def compile_batch(destination,*,execute=False):
    if not execute:return None
    need(sha(NATIVE)==NATIVE_SHA,'original native identity changed')
    need(not Path(destination).exists(),'fresh diagnostic library required')
    argv=['/usr/bin/g++','-std=c++17','-O2','-shared','-fPIC','-fno-fast-math',
      '-ffp-contract=off','-fno-tree-vectorize',str(HERE/'native_batch.cpp'),str(NATIVE),
      '-Wl,-rpath,'+str(NATIVE.parent),'-o',str(destination)]
    subprocess.run(argv,check=True,capture_output=True,timeout=30)
    return argv

class NativeBatch:
    def __init__(self,path):
        need(sha(NATIVE)==NATIVE_SHA,'native identity changed')
        self.lib=ctypes.CDLL(str(path));u=ctypes.POINTER(ctypes.c_uint32)
        self.lib.diagnostic_qk.argtypes=[u,u,ctypes.c_uint,u,u,u,u,ctypes.POINTER(ctypes.c_uint64)]
        self.lib.diagnostic_qk.restype=ctypes.c_int
    def run(self,q,k,rows=128):
        import numpy as np
        need(q.dtype==k.dtype==np.dtype('<f4') and q.shape==(128,1536) and k.shape==(128,256),'QK input format')
        need(q.flags.c_contiguous and k.flags.c_contiguous and type(rows) is int and 1<=rows<=128,'bounds/contiguity')
        parts=np.full((12,128,128,16),np.nan,dtype='<f4')
        outputs=[np.full((12,128,128),np.nan,dtype='<f4') for _ in range(3)]
        u=ctypes.POINTER(ctypes.c_uint32);count=ctypes.c_uint64()
        rc=self.lib.diagnostic_qk(*(x.ctypes.data_as(u) for x in (q,k)),rows,
            *(x.ctypes.data_as(u) for x in (parts,*outputs)),ctypes.byref(count))
        need(rc==0,'native QK status '+str(rc))
        need(count.value==12*rows*(rows+1)//2*8*512,'actual original FMA count')
        return dict(parts=parts,sums=outputs[0],dots=outputs[1],scores=outputs[2],fmas=count.value)
