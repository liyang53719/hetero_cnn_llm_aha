"""Compose the final identity and metadata-only diagnostic source overlay."""
import ast
import hashlib
from pathlib import Path
import subprocess
from ..raw_kv_public_recipe_runtime import prepare as previous
from . import launch
ROOT=Path(__file__).resolve().parents[3]
PREFIX=launch.PREFIX
PATCH=PREFIX+'launch_bridge.patch'
IMPORTED_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

def need(ok):
    if not ok:raise ValueError('paired launch preparation')

def rewrite(name,raw):
    text=raw.decode()
    if name in launch.HELPERS:
        old='from . import runtime';new='from ..raw_kv_public_recipe_run import launch as runtime'
        need(text.count(old)==(3 if name.endswith('/producer.py') else 1))
    else:
        alias='m128_runtime' if name==launch.SETUP else 'm128_profile'
        old='from ..raw_kv_public_recipe_runtime import runtime as '+alias
        new='from ..raw_kv_public_recipe_run import launch as '+alias
        need(text.count(old)==1)
    text=text.replace(old,new)
    if name==launch.SETUP:
        old_dispatch="'candidates.qwen2_resident_matrix.raw_kv_public_m128_run.launch'"
        need(text.count(old_dispatch)==1)
        text=text.replace(old_dispatch,"'candidates.qwen2_resident_matrix.raw_kv_public_recipe_run.launch'")
    return diagnostic_hooks(name,text).encode()

def diagnostic_hooks(name,text):
    def replace(old,new):
        nonlocal text
        need(text.count(old)==1);text=text.replace(old,new)
    if name==launch.prerequisite.ENTRY:
        replace('    s=verify_snapshot(path,digest',
                "    from candidates.qwen2_resident_matrix.raw_kv_public_recipe_run import numeric_progress\n    numeric_progress.stage('run_preflight')\n    s=verify_snapshot(path,digest")
        for marker,stage in (
            ("            inputs=prior.load_inputs(", 'input_load'),
            ("            report['prefix_execution']=", 'public_prefix'),
            ("            with capture:\n", 'public_suffix'),
            ("            report['observation']=capture.save(", 'observation_seal'),
            ("            gate.opened=True", 'comparison'),
            ("            require(source_hashes(", 'source_recheck'),
            ("            save();return report", 'save_receipt')):
            replace(marker,"            numeric_progress.stage('"+stage+"')\n"+marker)
        replace("            silu=policy.ObservedSiluLibrary(",
                "            numeric_progress.observe_trace(x.trace)\n            silu=policy.ObservedSiluLibrary(")
    return text

def check_bridge_scope(originals,generated):
    need(set(originals)==set(generated)==set(launch.TARGETS))
    for name in launch.TARGETS:
        expected=rewrite(name,originals[name])
        need(ast.dump(ast.parse(expected))==ast.dump(ast.parse(generated[name])))
        need(expected==generated[name])

def prepare(out,*,enable_raw_kv=True):
    need(type(enable_raw_kv) is bool and enable_raw_kv is True)
    out=Path(out)
    need(not out.exists() and not out.is_symlink() and all(not p.is_symlink() for p in out.parents))
    frozen=launch.contract_snapshot(composed=False)
    need(frozen['sources'][PREFIX+'prepare.py']==IMPORTED_SHA256)
    baseline=previous.prepare(out)
    need(all(frozen['sources'].get(n)==h for n,h in baseline['sources'].items()))
    need(all(frozen['generated'][n]==h for n,h in baseline['generated'].items() if n not in launch.TARGETS))
    for name in launch.HELPERS:
        destination=out/name;destination.parent.mkdir(parents=True,exist_ok=True)
        need(not destination.exists());destination.write_bytes(launch.read_source(name))
    originals={n:(out/n).read_bytes() for n in launch.TARGETS}
    raw=launch.read_source(PATCH)
    lines=raw.decode().splitlines()
    need([s for s in lines if s.startswith('--- ')]==['--- a/'+n for n in launch.TARGETS])
    need([s for s in lines if s.startswith('+++ ')]==['+++ b/'+n for n in launch.TARGETS])
    subprocess.run(['patch','--batch','--fuzz=0','-p1'],cwd=out,input=raw,check=True,capture_output=True,timeout=10)
    generated={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}
    need(generated==frozen['generated'])
    check_bridge_scope(originals,{n:(out/n).read_bytes() for n in launch.TARGETS})
    need(launch.contract_snapshot(composed=False)==frozen)
    return dict(status='PASS_PREPARATION_ONLY',inputs=frozen['sources'],generated=generated,numerical_execution=False,native_execution=False)
