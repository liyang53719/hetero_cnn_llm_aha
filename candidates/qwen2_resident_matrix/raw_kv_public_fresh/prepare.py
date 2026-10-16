"""Compose only the two explicitly fresh-provenance entry variants.

The disabled AST projection preserves the historical control/math/gate path.
Enabled provenance branches additionally require direct review and exact final
source hashes. No reference producer or numerical verifier is executed here.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from candidates.qwen2_resident_matrix.raw_kv_public_numeric import prepare as upstream

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE_COMMIT = '5a0b712d19bf4eebc429e342286643f423f14a58'
OFFICIAL = 'candidates/qwen2_resident_matrix/official_bf16/check_numeric.py'
ENTRY = upstream.ENTRY
FRESH_TARGETS = (OFFICIAL, ENTRY)
OWN_INPUTS = ('assets.py','official_entry.patch','public_entry.patch','prepare.py','pins.json','README.md','test_assets.py')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def _fresh_test(node):
    return (isinstance(node,ast.Name) and node.id == 'fresh_profile') or (
        ast.dump(node,include_attributes=False) == ast.dump(ast.parse(
            "ref.get('fresh_profile') == fresh_assets.PROFILE",mode='eval').body,include_attributes=False)) or (
        ast.dump(node,include_attributes=False) == ast.dump(ast.parse(
            "reference.get('fresh_profile') == fresh_assets.PROFILE",mode='eval').body,include_attributes=False))


class _HistoricalProjection(ast.NodeTransformer):
    """Historical disabled projection only; not a proof of enabled semantics."""
    def __init__(self, *, official):
        self.keywords = {'fresh_profile','fresh_manifest','fresh_manifest_sha256'}
        if official:
            self.keywords.add('enable_raw_kv')

    def visit_ImportFrom(self,node):
        if node.module == 'raw_kv_public_fresh':
            return None
        return node

    def visit_FunctionDef(self,node):
        pairs=[(arg,default) for arg,default in zip(node.args.kwonlyargs,node.args.kw_defaults)
               if arg.arg not in self.keywords]
        node.args.kwonlyargs=[a for a,_ in pairs];node.args.kw_defaults=[d for _,d in pairs]
        return self.generic_visit(node)

    def visit_If(self,node):
        if _fresh_test(node.test):
            result=[]
            for child in node.orelse:
                value=self.visit(child)
                if value is not None:result.extend(value if isinstance(value,list) else [value])
            return result
        return self.generic_visit(node)

    def visit_IfExp(self,node):
        return self.visit(node.orelse) if _fresh_test(node.test) else self.generic_visit(node)

    def visit_Compare(self,node):
        if _fresh_test(node):
            return ast.Constant(False)
        return self.generic_visit(node)

    def visit_Assign(self,node):
        if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and \
           isinstance(node.value.func.value,ast.Name) and node.value.func.value.id == 'fresh_assets':
            return None
        return self.generic_visit(node)

    def visit_Expr(self,node):
        call=node.value
        if isinstance(call,ast.Call):
            if ast.dump(call,include_attributes=False) == ast.dump(ast.parse('result.update(fresh_assets.own_sources())',mode='eval').body,include_attributes=False):return None
            if isinstance(call.func,ast.Attribute):
                if isinstance(call.func.value,ast.Name) and call.func.value.id == 'fresh_assets':return None
                if call.func.attr == 'add_argument' and call.args and isinstance(call.args[0],ast.Constant) and \
                   call.args[0].value in ('--fresh-profile','--fresh-manifest','--fresh-manifest-sha256'):return None
            if isinstance(call.func,ast.Name) and call.func.id == 'require' and len(call.args)>1 and \
               isinstance(call.args[1],ast.Constant) and call.args[1].value in (
                   'canonical fresh source modes required','canonical fresh profile flag required',
                   'run uses only frozen fresh manifest identity'):return None
        return self.generic_visit(node)

    def visit_Call(self,node):
        node.keywords=[item for item in node.keywords if item.arg not in self.keywords]
        return self.generic_visit(node)


def check_scope(originals, generated):
    need(set(originals) == set(generated) == set(FRESH_TARGETS), 'exact two fresh-entry targets required')
    for name in FRESH_TARGETS:
        before=ast.parse(originals[name]); after=_HistoricalProjection(official=name==OFFICIAL).visit(ast.parse(generated[name]))
        need(ast.dump(before,include_attributes=False) == ast.dump(after,include_attributes=False),
             'fresh patch exceeds historical disabled projection: '+name)


def prepare(out, *, enable_raw_kv=False):
    need(type(enable_raw_kv) is bool,'canonical raw KV source mode required')
    out=Path(out);need(not out.exists() and not out.is_symlink(),'fresh composition directory required')
    pins=json.loads((HERE/'pins.json').read_text())
    need(pins['schema']==1 and pins['base_commit']==BASE_COMMIT and pins['historical_assets_relabelled'] is False,
         'fresh preparation lineage differs')
    for name,expected in pins['input_blobs'].items():
        raw=(ROOT/name).read_bytes()
        need(blob(raw)==expected and sha(raw)==pins['source_sha256'][name],'fresh base source drift: '+name)
    baseline=upstream.prepare(out,enable_raw_kv=enable_raw_kv)
    official=out/OFFICIAL;official.parent.mkdir(parents=True,exist_ok=True);official.write_bytes((ROOT/OFFICIAL).read_bytes())
    originals={name:(out/name).read_text() for name in FRESH_TARGETS}
    for filename,target in (('official_entry.patch',OFFICIAL),('public_entry.patch',ENTRY)):
        raw=(HERE/filename).read_bytes()
        need(sha(raw)==pins['patch_sha256'][filename],'fresh entry patch drift')
        need([line[6:] for line in raw.decode().splitlines() if line.startswith('--- a/')] == [target],
             'fresh patch target scope differs')
        subprocess.run(['patch','--batch','--fuzz=0','-p1'],cwd=out,input=raw,check=True,capture_output=True,timeout=10)
    generated={name:(out/name).read_text() for name in FRESH_TARGETS}
    check_scope(originals,generated)
    hashes={str(path.relative_to(out)):sha(path.read_bytes()) for path in out.rglob('*') if path.is_file()}
    mode='enabled' if enable_raw_kv else 'disabled'
    need(hashes==pins['generated_sha256'][mode],'fresh generated source identity drift')
    own={str((HERE/name).relative_to(ROOT)) for name in OWN_INPUTS}
    need(set(pins['own_sources'])==own and set(pins['source_paths'])==set(pins['source_sha256'])|own,
         'exact fresh runtime source closure required')
    need(set(baseline['inputs']) <= set(pins['source_sha256']), 'upstream source omitted from fresh closure')
    inputs={name:sha((ROOT/name).read_bytes()) for name in pins['source_paths']}
    need(all(inputs[name]==expected for name,expected in pins['source_sha256'].items()),'fresh source changed during preparation')
    return dict(status='PASS_PREPARATION_ONLY',enable_raw_kv=enable_raw_kv,inputs=inputs,generated=hashes,
                fresh_targets=list(FRESH_TARGETS),historical_assets_relabelled=False,
                numerical_execution=False,native_execution=False)


def check(*,enable_raw_kv=False):
    with tempfile.TemporaryDirectory(prefix='raw-kv-fresh-source-') as directory:
        return prepare(Path(directory)/'sources',enable_raw_kv=enable_raw_kv)
