#!/usr/bin/env python3
"""Authenticate Host V fixture bytes by replaying the code-pinned source packer.

The caller cannot supply an NPZ, weight digest, source receipt, or expected
output. A self-consistent caller-edited manifest is insufficient.
"""
from pathlib import Path
import argparse,json,subprocess,sys,tempfile
from pack_host_bf16_v_fixture import pack_fixture, pinned_session, fixture_input_hashes, LEGACY_PINNED_SOURCES
ROOT=Path(__file__).resolve().parents[3]
PACKER=Path(__file__).with_name('pack_host_bf16_v_fixture.py')

def verify(fixture:Path,*,session=None)->dict:
    if fixture.is_symlink():raise ValueError('fixture root must not be a symlink')
    fixture=fixture.resolve()
    if not fixture.is_relative_to(ROOT/'work') or not fixture.is_dir():raise ValueError('fixture must be under ignored work')
    if any(p.is_symlink() for p in fixture.rglob('*')):raise ValueError('fixture contains symlinks')
    manifest=json.loads((fixture/'manifest.json').read_text())
    if session is None and (manifest.get('fresh_official_executions')!=0 or manifest.get('reused_official_executions')!=2):
        raise ValueError('fresh fixture requires its live same-invocation capture session')
    session=pinned_session() if session is None else session
    variant,phase,base,count=[manifest[k] for k in ('variant','phase','token_base','token_count')]
    if type(variant) is not str or variant not in ('baseline','avx2') or type(phase) is not str or phase not in ('cold','carried'):
        raise ValueError('invalid source selection')
    if type(base) is not int or type(count) is not int or not 0<=base<128 or not 1<=count<=128 or base+count>128:
        raise ValueError('invalid token window')
    with tempfile.TemporaryDirectory(prefix='.host_v_verify_',dir=ROOT/'work') as temporary:
        expected=Path(temporary)/'expected'
        pack_fixture(expected,variant=variant,phase=phase,token_base=base,token_count=count,session=session)
        canonical=json.loads((expected/'manifest.json').read_text())
        if not session.fresh and manifest.get('sources')==LEGACY_PINNED_SOURCES:
            canonical['sources']=LEGACY_PINNED_SOURCES
        if manifest!=canonical:raise ValueError('fixture manifest differs from authenticated source session')
        names={p.name for p in expected.iterdir()}
        if {p.name for p in fixture.iterdir()}!=names:raise ValueError('fixture inventory differs from authenticated packer')
        for name in names:
            if name=='manifest.json':continue # Already checked as a complete JSON object above.
            if not (fixture/name).is_file() or (fixture/name).read_bytes()!=(expected/name).read_bytes():
                raise ValueError('source-bound fixture bytes differ: '+name)
    return dict(status='PASS_FRESH_SAME_INVOCATION_HOST_V_FIXTURE' if session.fresh else 'PASS_CODE_PINNED_HOST_V_FIXTURE',
                variant=variant,phase=phase,token_base=base,token_count=count,input_sha256=fixture_input_hashes(fixture,manifest),
                **session.evidence())

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('fixture',type=Path);args=p.parse_args()
    try:print(json.dumps(verify(args.fixture),indent=2))
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as e:raise SystemExit('HOST_V_FIXTURE_REJECTED: '+str(e))
