"""Exact source-only identity. Neither this digest nor local data grants approval."""
import hashlib
import json
from pathlib import Path
from candidates.qwen2_fullblock_ci_dut import closure as old
from candidates.qwen2_fullblock_ci_execution import closure as BASE
from candidates.qwen2_official_cpu_platform_reference import policy as P, validator as V
ROOT=Path(__file__).resolve().parents[2]
PACKAGE='candidates/qwen2_official_platform_fullblock'
WORKFLOW='.github/workflows/qwen2-official-platform-fullblock.yml'
CACHE='candidates/qwen2_cold_cache_contract_candidate'
CACHE_SHA='5e23f497cab4591df85318535ff6744215e48d80576e5881a80dad06cf845741'


def _add(result,root,name):
    path=root/name
    if path.resolve()!=path or any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('source alias')
    raw=path.read_bytes();result[name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def source_manifest(root=ROOT):
    root=Path(root)
    if root!=ROOT:raise ValueError('fixed source root')
    # Includes the immutable original driver, all 232 surviving dependencies,
    # original observer receipt, statistics/tail/runtime/platform and supervisor.
    result=BASE.source_manifest(root)
    result.update(old.preserved_sources(root))
    old_dir=root/'candidates/qwen2_fullblock_ci_dut'
    old_manifest=json.loads((old_dir/'SOURCE_MANIFEST.json').read_bytes())
    for name,spec in old_manifest['files'].items():
        relative='candidates/qwen2_fullblock_ci_dut/'+name
        _add(result,root,relative)
        if result[relative]!=spec:raise ValueError('preserved DUT source changed')
    _add(result,root,'candidates/qwen2_fullblock_ci_dut/SOURCE_MANIFEST.json')
    for name in ('candidates/qwen2_ci_prepare_diagnostic/diagnostic.py',
                 'candidates/qwen2_supervisor_recovery/launch.py',
                 'candidates/qwen2_supervisor_recovery/observation.py',
                 'candidates/qwen2_retained_write_recovery/debts.py'):_add(result,root,name)
    V.source_digest(root)
    for name in (*P.FILES,'SOURCE_MANIFEST.json'):_add(result,root,P.PACKAGE+'/'+name)
    _add(result,root,P.PAIR_WORKFLOW)
    _add(result,root,WORKFLOW)
    directory=root/PACKAGE
    manifest=json.loads((directory/'SOURCE_MANIFEST.json').read_bytes())
    if set(manifest)!={'schema','files'} or type(manifest['schema']) is not int or manifest['schema']!=1:
        raise ValueError('exact source manifest')
    present={str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()}
    if present!=set(manifest['files'])|{'SOURCE_MANIFEST.json'}:raise ValueError('exact sibling inventory')
    for name,spec in manifest['files'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('source inventory path')
        _add(result,root,PACKAGE+'/'+name)
        if result[PACKAGE+'/'+name]!=spec:raise ValueError('sibling source drift')
    _add(result,root,PACKAGE+'/SOURCE_MANIFEST.json')
    for name in ('compare.py','test_compare.py','README.md'):_add(result,root,CACHE+'/'+name)
    if result[CACHE+'/compare.py']['sha256']!=CACHE_SHA:raise ValueError('reviewed cache comparison source drift')
    return result


def digest(root=ROOT):
    return hashlib.sha256(json.dumps(source_manifest(root),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
