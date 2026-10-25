"""Isolated stdlib-only reader of one retained SV; importing starts no work.

The admitted checker is read-only source. This is not a filesystem sandbox:
read-only behavior follows reviewed code plus before/after pinned-input checks.
No native/EDA/JVM execution, SV generation, signal sampling or retry occurs here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import types

SCHEMA = 'qwen2-core-client-retained-sv-offline-supervisor-v1'
SUCCESS = 'PASS_RETAINED_SV_STRUCTURE_ONLY'
SV_BYTES = 26251369
SV_SHA = '77f61549b4aebd109362d30164f95422b9192d0a8b2b1599942a9360852f9225'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def verify(item):
    path=Path(item['path'])
    need(path.is_absolute() and path.is_file(), 'absolute regular pinned input')
    need(path.is_symlink()==('symlink_target' in item), 'pinned symlink kind')
    if path.is_symlink():
        need(os.readlink(path)==item['symlink_target'], 'pinned symlink target')
    if 'resolved_path' in item:
        need(str(path.resolve())==item['resolved_path'], 'pinned resolved path')
    need(path.stat().st_size==item['bytes'], 'pinned length')
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            h.update(chunk)
    need(h.hexdigest()==item['sha256'], 'pinned digest')


def run_check(manifest):
    """Internal testable reader; production main fixes source/input identity first."""
    root=Path(manifest['run_root'])
    sv=manifest['retained_sv'];anno=manifest['annotation_absent_path']
    need(not os.path.lexists(anno), 'retained annotation unexpectedly exists before check')
    verify(sv)
    checker=manifest['structure_checker'];verify(checker)
    expectation_file=manifest['structure_expectation_file'];verify(expectation_file)
    expectation=json.loads(Path(expectation_file['path']).read_text())
    need(expectation==manifest['structure_expectation'], 'frozen expectation mismatch')
    raw=Path(checker['path']).read_bytes()
    need(len(raw)==checker['bytes'] and hashlib.sha256(raw).hexdigest()==checker['sha256'], 'checker read identity')
    module=types.ModuleType('admitted_retained_sv_checker');module.__file__=checker['path']
    exec(compile(raw,checker['path'],'exec'),module.__dict__)
    checked=module.check_retained(Path(sv['path']),Path(anno),expectation)
    need(type(checked) is dict and checked.get('status')==manifest['structure_success_status'], 'retained SV checker rejected')
    need(checked.get('sv_bytes')==sv['bytes'] and checked.get('sv_sha256')==sv['sha256'] and checked.get('top')==expectation['top'] and checked.get('behavior_pass') is False and checked.get('numerical_pass') is False, 'inner checked SV identity/top/scope binding')
    verify(sv);verify(checker);verify(expectation_file)
    need(not os.path.lexists(anno), 'retained annotation unexpectedly exists after check')
    result=dict(status=manifest['structure_success_status'],input_sv=sv,annotation_absent_path=anno,
                annotation_absent_before_after=True,input_unchanged_before_after=True,
                no_target_execution=True,offline_only=True,behavior_pass=False,numerical_pass=False,check=checked)
    encoded=(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
    need(len(encoded)<=manifest['caps']['single_file_hard_bytes'], 'bounded worker RESULT bytes')
    with (root/'RESULT.json').open('xb') as stream:
        stream.write(encoded);stream.flush()
        need(os.fstat(stream.fileno()).st_size==len(encoded), 'worker RESULT final size')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True)
    args=parser.parse_args(argv)
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'required Python -I -S -B')
    raw=args.manifest.read_bytes()
    need(hashlib.sha256(raw).hexdigest()==args.manifest_sha256, 'exact admitted manifest')
    m=json.loads(raw)
    need(m['schema']==SCHEMA and m['stage']=='retained-sv-offline-only' and m['structure_success_status']==SUCCESS, 'offline-only worker schema/status')
    need(m['retained_sv']['bytes']==SV_BYTES and m['retained_sv']['sha256']==SV_SHA, 'exact retained actual SV input')
    need(m['worker_source']['path']==str(Path(__file__).resolve()), 'exact worker source path')
    verify(m['worker_source']);verify(m['python_executable'])
    need(Path(sys.executable).resolve()==Path(m['python_executable']['path']).resolve(), 'exact Python executable')
    root=Path(m['run_root'])
    need(root.is_dir() and not root.is_symlink() and Path.cwd()==root, 'claimed new output cwd')
    claim_path=root/'CLAIM.json'
    need(claim_path.is_file() and not claim_path.is_symlink(), 'regular consumed supervisor claim')
    claim=json.loads(claim_path.read_text())
    expected_argv=[value.replace('${NEW_RUN_ROOT}',str(root)).replace('${MANIFEST_PATH}',str(args.manifest.absolute())).replace('${MANIFEST_SHA256}',args.manifest_sha256) for value in m['worker_argv']]
    need(expected_argv==[m['python_executable']['path'],'-I','-S','-B',m['worker_source']['path'],'--manifest',str(args.manifest.absolute()),'--manifest-sha256',args.manifest_sha256], 'exact rendered isolated worker command')
    need(sys.argv==expected_argv[4:], 'exact current worker script arguments')
    need(claim['schema']==SCHEMA and claim['stage']=='retained-sv-offline-only' and claim['consumed'] is True and claim['parent_pid']==os.getppid() and claim['argv']==expected_argv and claim['argv_template']==m['worker_argv'], 'current parent-owned claim')
    run_check(m)
    print(SUCCESS,flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
