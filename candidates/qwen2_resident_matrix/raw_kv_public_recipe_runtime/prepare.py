"""Apply the exact three-target Public producer/admission overlay, source-only."""
import ast
from pathlib import Path
import subprocess
from ..raw_kv_public_m128_run import prepare as previous
from . import runtime

ROOT=Path(__file__).resolve().parents[3]
PATCH=runtime.PREFIX+'runtime.patch'


def need(ok):
    if not ok:raise ValueError('Public paired overlay scope')


def check_scope(originals,generated):
    """Unchanged whole-AST outside explicit control/provenance nodes.

    Exact generated hashes separately constrain all changed nodes; this projection
    alone does not prove their enabled behavior.
    """
    need(set(originals)==set(generated)==set(runtime.TARGETS))
    rules={runtime.TARGETS[0]:({'PROFILE','NATIVE_PRODUCER'},{'validate_manifest','_verify_native_record','_views'}),
        runtime.TARGETS[1]:(set(),{'run'}),
        runtime.TARGETS[2]:({'PHASE_LIMITS'},{'run','_phase_native16','_phase_native128','_phase_seal','internal_phase'})}
    for name in runtime.TARGETS:
        before=ast.parse(originals[name]);after=ast.parse(generated[name]);assigns,functions=rules[name]
        alias='m128_runtime' if name==runtime.TARGETS[2] else 'm128_profile'
        old_import=ast.parse('from ..raw_kv_public_m128_run import launch as '+alias).body[0]
        new_import=ast.parse('from ..raw_kv_public_recipe_runtime import runtime as '+alias).body[0]
        def rest(tree,import_node):
            result=[];seen=set()
            for node in tree.body:
                if ast.dump(node)==ast.dump(import_node):seen.add('import');continue
                if isinstance(node,ast.FunctionDef) and node.name in functions:seen.add(node.name);continue
                if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in assigns:
                    seen.add(node.targets[0].id);continue
                result.append(ast.dump(node))
            need(seen==assigns|functions|{'import'});return result
        need(rest(before,old_import)==rest(after,new_import))


def prepare(out):
    out=Path(out)
    need(not out.exists() and not out.is_symlink() and all(not p.is_symlink() for p in out.parents))
    frozen=runtime.contract_snapshot(composed=False)
    baseline=previous.prepare(out,enable_raw_kv=True)
    need(all(frozen['sources'].get(n)==h for n,h in baseline['inputs'].items()))
    need(all(frozen['generated'][n]==h for n,h in baseline['generated'].items() if n not in runtime.TARGETS))
    originals={n:(out/n).read_bytes() for n in runtime.TARGETS}
    raw=runtime.read_source(PATCH)
    lines=raw.decode().splitlines()
    need([s for s in lines if s.startswith('--- ')]==['--- a/'+n for n in runtime.TARGETS])
    need([s for s in lines if s.startswith('+++ ')]==['+++ b/'+n for n in runtime.TARGETS])
    subprocess.run(['patch','--batch','--fuzz=0','-p1'],cwd=out,input=raw,check=True,capture_output=True,timeout=10)
    generated=previous.previous._inventory(out)
    need(generated==frozen['generated'])
    check_scope(originals,{n:(out/n).read_bytes() for n in runtime.TARGETS})
    need(runtime.contract_snapshot(composed=False)==frozen)
    return dict(status='PASS_SOURCE_COMPOSITION',sources=frozen['sources'],generated=generated,
        public_execution_enabled=False,numerical_execution=False,native_execution=False)
