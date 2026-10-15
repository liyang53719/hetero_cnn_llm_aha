"""Source-only CI closure. Never includes work, outputs, runtime or certificates."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PACKAGES=('qwen2_fullblock_ci_execution','qwen2_fullblock_ci_reference','qwen2_fullblock_ci_prepare')
SUFFIXES={'.py','.json','.md','.txt','.yml'}
WORKFLOW='.github/workflows/qwen2-fullblock-ci-bootstrap.yml'

def source_manifest(root=ROOT):
    root=Path(root)
    names={WORKFLOW,'.github/workflows/qwen2-reference-ci-diagnostic.yml',
           'candidates/qwen2_ci_prepare_diagnostic/diagnostic.py','candidates/qwen2_fullblock_reference_m128/pins.json',
           'candidates/qwen2_fullblock_reference_m128/FROZEN_CONTRACT.json'}
    for package in PACKAGES:
        directory=root/'candidates'/package
        for path in directory.iterdir():
            if path.suffix in SUFFIXES and path.is_file():names.add(str(path.relative_to(root)))
    original=json.loads((root/'candidates/qwen2_fullblock_reference_m128/pins.json').read_bytes())
    for spec in original['preserved_execution_closures'].values():
        names.update(name for name in spec['sha256'] if not name.startswith('work/'))
    names.update(name for name in original['sources'] if not name.startswith('work/'))
    dependency=root/'candidates/qwen2_fullblock_ci_reference/dependencies.json'
    names.update(json.loads(dependency.read_bytes()))
    from . import inputs,native,platform
    names.update(inputs.SOURCE_HASHES);names.update(native.SOURCE_HASHES);names.update(platform.SOURCES)
    result={}
    for name in sorted(names):
        if name.startswith('work/') or Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('non-source namespace in source closure')
        path=root/name
        if path.resolve()!=path or any(p.is_symlink() for p in (path,*path.parents)):
            raise ValueError('aliased source closure file')
        raw=path.read_bytes()
        result[name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    return result

def digest(root=ROOT):
    raw=json.dumps(source_manifest(root),sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()
