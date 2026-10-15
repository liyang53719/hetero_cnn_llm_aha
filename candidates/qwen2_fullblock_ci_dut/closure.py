"""Source-only DUT closure extends immutable bootstrap sources with this sibling.

No runtime, outputs, authorization certificates or local execution receipts are
included. Its digest is an identity, never self-issued permission to execute.
"""
import hashlib
import json
from pathlib import Path
from candidates.qwen2_fullblock_ci_execution import closure as bootstrap
ROOT=Path(__file__).resolve().parents[2]
PACKAGE='candidates/qwen2_fullblock_ci_dut'
BOOTSTRAP_SHA='10133c5fdd94f058f5397d03f2ae6a8dd87e2bdfa8b15a4d436dd87af1b78321'



def preserved_sources(root):
    pin='candidates/qwen2_live_fullblock_model_m128/pins.json'
    raw=(root/pin).read_bytes()
    if hashlib.sha256(raw).hexdigest()!='a8085fe405084b4b415ae4927d85148f698b1437c05c69cbe2e07dc2feaac9f8':
        raise ValueError('original fullblock source pin changed')
    expected={name:value for name,value in json.loads(raw)['dependency_sha256'].items()
              if not name.startswith('work/')}
    expected['candidates/qwen2_resident_matrix/ffn_public/fullgraph_numerical_receipt.json']='3d0f449d3e2a62f87ea915d89930dc5788f0ea835b11ce265a169c1fc4e5570e'
    result={pin:dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())}
    for name,digest in expected.items():
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('non-source preserved identity')
        path=root/name
        if path.resolve()!=path or any(p.is_symlink() for p in (path,*path.parents)):
            raise ValueError('preserved source alias')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('preserved source changed')
        result[name]=dict(bytes=len(raw),sha256=digest)
    return result

def source_manifest(root=ROOT):
    root=Path(root)
    if bootstrap.digest(root)!=BOOTSTRAP_SHA:
        raise ValueError('immutable bootstrap source closure changed')
    result=bootstrap.source_manifest(root)
    result.update(preserved_sources(root))
    for name in ('.github/workflows/qwen2-fullblock-ci-dut.yml',
                 'candidates/qwen2_ci_prepare_diagnostic/diagnostic.py',
                 'candidates/qwen2_supervisor_recovery/launch.py',
                 'candidates/qwen2_supervisor_recovery/observation.py',
                 'candidates/qwen2_retained_write_recovery/debts.py'):
        path=root/name
        if path.resolve()!=path or any(p.is_symlink() for p in (path,*path.parents)):
            raise ValueError('support source alias')
        raw=path.read_bytes()
        result[name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    directory=root/PACKAGE
    for path in sorted(directory.rglob('*')):
        if path.is_dir():
            if path.name=='__pycache__':
                raise ValueError('unreviewed generated source directory')
            continue
        if path.resolve()!=path or any(p.is_symlink() for p in (path,*path.parents)):
            raise ValueError('source alias')
        if path.suffix not in {'.py','.json','.md','.txt'}:
            raise ValueError('unexpected DUT source file')
        raw=path.read_bytes()
        result[str(path.relative_to(root))]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    return result


def digest(root=ROOT):
    raw=json.dumps(source_manifest(root),sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()
