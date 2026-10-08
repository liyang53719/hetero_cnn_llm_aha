#!/usr/bin/env python3
"""Fresh pinned official prefix -> actual production Host V-only acceptance.

The frozen materializer executes baseline and AVX2 in fresh interpreters. Its
returned digest stays in this top-level invocation through packing, admission,
actual token1 pass/fault runs and optional four full128 replays. Saved captures,
NPZs, caller trust hashes and external expected outputs are not CLI inputs.

Upload ONLY compact/summary.json and compact/source_input_hashes.json. All raw
captures, weights, tensors, generated RTL, executables and logs remain outside
that strict two-file JSON allowlist. This is a runnable entrypoint, not evidence
that fresh execution has already passed on any machine.
"""
from pathlib import Path
import argparse,contextlib,hashlib,json,os,subprocess,sys
from pack_host_bf16_v_fixture import rebuild_session,pack_fixture
from verify_host_bf16_v_fixture import verify
from host_bf16_v_execution import run_representative,verify_all_build_sources
from run_host_bf16_v_replays import run_replays
from prepare_idma_export import verify as verify_idma_export
ROOT=Path(__file__).resolve().parents[3]
SCRIPT_DIR=Path(__file__).resolve().parent
HOST_SOURCES=('pack_host_bf16_v_fixture.py','verify_host_bf16_v_fixture.py','host_bf16_v_execution.py',
    'run_host_bf16_v_replays.py','host_bf16_v_toolchain.py','run_host_bf16_v_gate.sh','run_host_bf16_v_fresh_gate.py','host_bf16_v_descriptor.py')
EXTRA_SOURCES=('chisel/continuous_prefill/config/host_bf16_v_descriptor_contract.json',
    'src/heteronpu/abi_validation.py','src/heteronpu/command.py','src/heteronpu/descriptor_chain.py',
    'src/heteronpu/gemmini_descriptor_v2.py','src/heteronpu/gemmini_rocc_lowering.py')
COMPACT_FILES=frozenset(('summary.json','source_input_hashes.json'))

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def _git_head():
    return subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()

def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--payload-layer0',type=Path,default=ROOT/'work/qwen35_layer0_payload')
    p.add_argument('--payload-layer3',type=Path,default=ROOT/'work/qwen35_layer3_payload')
    p.add_argument('--payload-extra',type=Path,default=ROOT/'work/qwen35_prefix_payload')
    p.add_argument('--burst',choices=('0','1'),default='0')
    p.add_argument('--full128',action='store_true',help='After token1 pass/faults, reuse the same DUT for baseline/AVX2 x cold/carried, all128 rows')
    return p

def _native_failure_evidence(session):
    session.verify()
    evidence={}
    for variant in ('baseline','avx2'):
        report=json.loads((session.directory/variant/'native/result.json').read_text())
        evidence[variant]=dict(status=report['status'],gate_pass=report['gate_pass'],thresholds=report['thresholds'],
            failed_producers=report['failed_producers'],
            failed_softmax_invariants=[x for x in report['softmax_invariants'] if not x['pass']])
    return evidence

def _write_compact(out,summary,hashes):
    compact=out/'compact'
    if compact.is_symlink():raise ValueError('compact directory must not be a symlink')
    compact.mkdir(exist_ok=True)
    if any(p.name not in COMPACT_FILES or p.is_symlink() or not p.is_file() for p in compact.iterdir()):
        raise ValueError('compact upload directory contains non-allowlisted content')
    payload=json.dumps(summary,sort_keys=True,indent=2)+'\n'
    (out/'summary.json').write_text(payload);(compact/'summary.json').write_text(payload)
    (compact/'source_input_hashes.json').write_text(json.dumps(hashes,sort_keys=True,indent=2)+'\n')
    if {p.name for p in compact.iterdir()}!=COMPACT_FILES:raise ValueError('compact inventory mismatch')

def _preflight(env,out):
    if env.get('BUILD_JOBS','1') not in ('1','2'):raise ValueError('BUILD_JOBS must be1 or2; default is1')
    export=env.get('IDMA_EXPORT')
    if not export or not (Path(export)/'idma.f.in').is_file():raise ValueError('IDMA_EXPORT must identify the verified pinned iDMA source export')
    return verify_idma_export(Path(export),out/'idma_preflight')

def run(args):
    original=Path(args.output)
    if original.is_symlink():raise ValueError('output must not be a symlink')
    out=original.resolve()
    if not out.is_relative_to(ROOT/'work') or out==ROOT/'work' or out.exists():
        raise ValueError('new output beneath ignored work required; existing evidence is never overwritten')
    out.mkdir(parents=True)
    host_sources={str((SCRIPT_DIR/name).relative_to(ROOT)):sha(SCRIPT_DIR/name) for name in HOST_SOURCES}
    host_sources.update({name:sha(ROOT/name) for name in EXTRA_SOURCES})
    hashes={'source_sha256':dict(host_sources),'input_sha256':{},'output_sha256':{}}
    summary=dict(status='FAIL_FRESH_PRODUCTION_HOST_V_ONLY',stage='preflight',actual_host_root=True,
        experimental_default_off=True,q_k_supported=False,full_block_supported=False,
        cross_host_byte_equivalence_claimed=False,capture_verification_succeeded=False,
        fresh_official_executions=None,reused_official_executions=0,requested_full128=bool(args.full128),
        artifact_upload_allowlist=['compact/summary.json','compact/source_input_hashes.json'])
    session=None
    try:
        env=os.environ.copy();env.setdefault('BUILD_JOBS','1');env['SOURCE_IDENTITY_SCOPE']='full'
        head=_git_head();summary['git_head']=head
        if env.get('GITHUB_SHA') and env['GITHUB_SHA']!=head:raise ValueError('checkout HEAD does not match GITHUB_SHA')
        summary['idma_preflight']=_preflight(env,out)
        with (out/'pipeline.log').open('w') as pipeline,contextlib.redirect_stdout(pipeline):
            summary['stage']='fresh_official_prefix_capture'
            session=rebuild_session(out/'official_capture',args.payload_layer0,args.payload_layer3,args.payload_extra)
            summary.update(session.evidence());summary['capture_verification_succeeded']=True
            hashes['source_sha256'].update(session.verify()['source_sha256'])
            summary['native_full_block_failures']=_native_failure_evidence(session)
            hashes['official_capture_manifest_sha256']=session.manifest_sha256
            summary['stage']='representative_fixture'
            fixture=out/'token1_fixture'
            pack_fixture(fixture,variant='baseline',phase='cold',token_base=0,token_count=1,session=session)
            admitted=verify(fixture,session=session)
            hashes['input_sha256']['baseline_cold_token1']=admitted['input_sha256']
            summary['stage']='production_host_build_only'
            build=out/'host_build'
            with (out/'host_build.log').open('w') as log:
                subprocess.run(['bash',str(SCRIPT_DIR/'run_host_bf16_v_gate.sh'),'--build-only',str(build),args.burst],
                    cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
            summary['toolchain']=json.loads((build/'toolchain.json').read_text())
            # No fresh authority is sent to the build-only child. Admission and
            # all numerical acceptance remain in this live Python invocation.
            summary['stage']='representative_actual_host_and_faults'
            representative=run_representative(build,fixture,session)
            summary['representative']=representative
            hashes['output_sha256']['baseline_cold_token1']=representative['actual_sha256']
            hashes['binary_sha256']=representative['binary_sha256'];hashes['rtl_sha256']=representative['rtl_sha256']
            compiled=json.loads((build/'sources.sha256.json').read_text())
            hashes['source_sha256'].update(compiled)
            for name in ('hardfloat.sha256.json','compiler_jars.sha256.json','idma_identity.json'):
                if (build/name).is_file():hashes[name.replace('.','_')+'_sha256']=sha(build/name)
            if args.full128:
                summary['stage']='four_full128_actual_host_replays'
                replay=run_replays(build,out/'full128',full128=True,only_full128=True,session=session)
                if len(replay['cases'])!=4:raise ValueError('expected exactly four full128 cases')
                summary['full128_cases']=replay['cases']
                for case in replay['cases']:
                    hashes['input_sha256'][case['name']]=case['input_sha256']
                    hashes['output_sha256'][case['name']]=case['actual_sha256']
            summary['stage']='final_source_and_capture_verification'
            session.verify()
            verify_all_build_sources(build,'fresh_final_source_verify.log')
            if any(sha(ROOT/name)!=digest for name,digest in host_sources.items()):raise ValueError('Host entrypoint source changed during execution')
            summary['native_full_block_failures']=_native_failure_evidence(session)
            summary.update(session.evidence())
            if _git_head()!=head:raise ValueError('git HEAD changed during fresh Host invocation')
            summary['git_head_verified_unchanged']=True
        summary.update(status='PASS_FRESH_PRODUCTION_HOST_V_ONLY'+('_FULL128' if args.full128 else '_TOKEN1'),stage='complete')
        _write_compact(out,summary,hashes)
        return summary,0
    except (Exception,KeyboardInterrupt) as exc:
        summary['error']=dict(type=type(exc).__name__,message=str(exc))
        summary['status']='FAIL_FRESH_PRODUCTION_HOST_V_ONLY'
        # Preserve the original failure and all raw native reports. A failed
        # recheck must never mint a replacement capture trust digest.
        if session is not None:
            try:
                summary.update(session.evidence())
                summary['native_full_block_failures']=_native_failure_evidence(session)
            except Exception as drift:
                summary['final_capture_verification_error']=str(drift)
                summary['capture_verification_succeeded']=False
        # Failed CI builds still retain available dependency/tool facts without
        # uploading the corresponding source, binary, RTL or tensor artifacts.
        partial={}
        for key,name in (('tools','toolchain_before.json'),('compiler_jars_sha256','compiler_jars.sha256.json'),
                         ('hardfloat_source_sha256','hardfloat.sha256.json'),('idma_identity','idma_identity.json'),
                         ('verilator_runtime','verilator_runtime.json')):
            path=out/'host_build'/name
            if path.is_file():
                try:partial[key]=json.loads(path.read_text())
                except (ValueError,OSError):pass
        if partial and 'toolchain' not in summary:summary['partial_build_toolchain']=partial
        _write_compact(out,summary,hashes)
        return summary,1

def main():
    args=parser().parse_args()
    try:summary,code=run(args)
    except (ValueError,OSError) as exc:
        print(json.dumps(dict(status='FRESH_HOST_V_ENTRY_REJECTED',error=str(exc)),sort_keys=True));raise SystemExit(2)
    print(json.dumps(summary,sort_keys=True,separators=(',',':')))
    raise SystemExit(code)

if __name__=='__main__':main()
