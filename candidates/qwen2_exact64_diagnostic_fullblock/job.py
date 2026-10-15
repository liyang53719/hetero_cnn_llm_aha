"""One 75-minute job under new external fixed source-policy approval; no defaults."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
import time
from candidates.qwen2_fullblock_ci_execution import inputs
from candidates.qwen2_official_cpu_platform_reference import pair, validator, policy
from . import closure
ROOT=Path(__file__).resolve().parents[2]
AUTH='candidates/qwen2_exact64_diagnostic_fullblock_authorization'
LOGS='work/exact64_diagnostic_fullblock_internal_logs'
OUT='work/qwen2_exact64_diagnostic_fullblock_numeric/ci01'
PACKAGE='candidates/qwen2_exact64_diagnostic_fullblock'
SUMMARY='work/qwen2_exact64_diagnostic_fullblock_summary.json'
CLOSURE_ENV='QWEN2_EXACT64_DIAGNOSTIC_SOURCE_CLOSURE_SHA256'
START_ENV='QWEN2_EXACT64_JOB_STARTED_MONOTONIC_NS'
POLICY=dict(schema=1,status='APPROVED_SINGLE_CI_M128_DIAGNOSTIC_SOFTWARE_OWNER_POLICY',
    scope='DIAGNOSTIC_SOFTWARE_OWNER',performance='NO_GO',hardware_mapping='NOT_IMPLEMENTED',
    chisel_full_prefill_pass=False,formal_fullblock_acceptance=False,job_total_minutes=75,
    actual_step_seconds=3720,postseal_gate_invocations=2,postseal_gate_inner_seconds=120,
    postseal_gate_outer_seconds=122,postseal_gate_cpu_seconds=120,postseal_gate_rss_bytes=2147483648,
    postseal_gate_file_bytes=33554432,postseal_gate_output_bytes=67108864,
    reference_invocations=2,reference_inner_seconds=120,reference_outer_seconds=122,
    dut_inner_seconds=3300,dut_outer_seconds=3330,maximum_invocations=1,no_retry=True,
    contract_id=policy.policy()['contract_id'],
    freeze_rule='TWO_FRESH_SEALED_SEMANTIC_VALID_29_BYTE_EQUAL_SAME_SOURCE_RAW_NATIVE_LIBPYTHON',
    future_private_bytes_reviewed=False,legacy_expected_hashes='DIAGNOSTIC_ONLY',
    cache_rule='SEALED_SAME_RUN_KV_EXACT_COPY_AND_UNCHANGED_OPERATOR_GATES')


def need(ok,message):
    if not ok:raise ValueError(message)


def authorize():
    need(ROOT==inputs.CI_ROOT,'fixed CI root')
    path=inputs.safe_path(ROOT,AUTH+'/DUT_REVIEW.json')
    need(0<path.stat().st_size<=16384,'bounded independent review')
    value=validator.parse(path.read_bytes())
    need(type(value) is dict and set(value)==set(POLICY)|{'source_closure_sha256',
        'reference_source_closure_sha256','reference_certificates','reviewer'},'exact external source policy review')
    need(all(type(value[k]) is type(v) and value[k]==v for k,v in POLICY.items()),'fixed policy/budgets')
    need(type(value['reviewer']) is str and value['reviewer'].startswith('/root/review_'),'independent reviewer')
    for key in ('source_closure_sha256','reference_source_closure_sha256'):
        validator.digest(value[key]);need(value[key]!='0'*64,'real external digest')
    certs=value['reference_certificates']
    need(type(certs) is dict and set(certs)==set(pair.RUNS),'two explicitly reviewed invocations')
    for digest in certs.values():validator.digest(digest);need(digest!='0'*64,'real new certificate')
    need(len(set(certs.values()))==2,'distinct fresh reference certificates')
    need(closure.digest(ROOT)==value['source_closure_sha256'],'reviewed exact new source')
    need(validator.source_digest(ROOT)==value['reference_source_closure_sha256'],'reviewed immutable official source')
    need(os.getenv('GITHUB_RUN_ATTEMPT')=='1','one CI attempt only')
    need(os.getenv('QWEN2_CI_RUNTIME_PROFILE')==policy.PROFILE and os.getenv('ATEN_CPU_CAPABILITY')=='avx2','explicit official profile')
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    need(actual==os.getenv('GITHUB_SHA'),'checked out CI source commit')
    expected=value['source_closure_sha256']
    need(os.getenv(CLOSURE_ENV) in (None,'',expected),'DUT closure environment conflict')
    os.environ[CLOSURE_ENV]=expected
    return value


def reference_authority(value):
    # Only this source-reviewed constant changes the pair's certificate search.
    # Captures, namespaces, issuer protocol and one-use certificates stay intact.
    need(pair.AUTH in ('candidates/qwen2_official_cpu_platform_authorization',AUTH),'unexpected pair AUTH rebind')
    pair.AUTH=AUTH
    for run in pair.RUNS:
        pins,_=pair.authorization(run)
        need(pins==dict(schema=1,certificate_sha256=value['reference_certificates'][run],
            source_closure_sha256=value['reference_source_closure_sha256']),'reviewed same-job reference authority')


def admit():
    value=authorize();reference_authority(value)
    pair.admit()
    start=os.getenv(START_ENV,'')
    need(start.isascii() and start.isdigit() and 0<int(start)<=time.monotonic_ns(),
         'first-step monotonic job clock required')
    return 'SINGLE_JOB_SOURCE_POLICY_ADMITTED'


def capture():
    value=authorize();reference_authority(value)
    result=pair.capture()
    need(result['status']=='NEW_REFERENCE_PAIR_EQUAL_PENDING_REVIEW' and
        result['checked_outputs']==result['equal_outputs']==29,'complete equal fresh pair required')
    return 'TWO_FRESH_REFERENCES_VERIFIED_LOCALLY'


def bind():
    from . import recipe
    return recipe.bind_pair(execute=True)


def bounded_child(argv,stream,outer_seconds):
    """One fresh child group; the outer bound includes two seconds of reaping."""
    from candidates.qwen2_supervisor_recovery.observation import SignalScope
    from candidates.qwen2_live_attention_model_m128_bounded.v2.launch import group_exists,terminate_group
    started=time.monotonic();deadline=started+outer_seconds;child=None;signals=SignalScope()
    timed_out=False;cleanup_incomplete=False
    try:
        signals.start()
        child=subprocess.Popen(argv,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        signals.check()
        while child.poll() is None:
            signals.check()
            if time.monotonic()>=deadline-2:
                timed_out=True;break
            time.sleep(.05)
        signals.check()
    finally:
        signals.cleaning()
        try:
            if child is not None and group_exists(child.pid):
                _,cleanup_incomplete=terminate_group(child,cleanup_deadline=deadline)
        finally:signals.stop()
    need(not timed_out,'bounded child outer wall limit')
    need(not cleanup_incomplete,'bounded child process group cleanup incomplete')
    need(child is not None and child.poll() is not None,'bounded child terminal missing')
    return child.returncode


def require_remaining(start_ns,step_started,seconds):
    now=time.monotonic()
    remaining=min(POLICY['job_total_minutes']*60-(now-start_ns/1e9),
                  POLICY['actual_step_seconds']-(now-step_started))
    need(remaining>=seconds,'insufficient joint job/actual-step budget')
    return remaining


def actual():
    step_started=time.monotonic()
    value=authorize()
    start=os.getenv(START_ENV,'')
    need(start.isascii() and start.isdigit() and 0<int(start)<=time.monotonic_ns(),'same-job monotonic clock required')
    remaining=4500-(time.monotonic_ns()-int(start))/1e9
    need(remaining>=3720,'insufficient total budget for diagnostic actual step')
    from . import exact64_artifact
    exact64_artifact.build()
    from . import recipe
    bound=bind()
    need(bound['status']==recipe.STATUS and bound['reference_outputs_checked']==29 and
        bound['policy_conditions_satisfied'] is True,'successful conditional binder required')
    # Consume the validator return directly. Never derive another launch pin by
    # rehashing a possibly changed file after the successful validation.
    os.environ[recipe.BINDING_ENV]=bound['binding_sha256']
    probe=inputs.safe_path(ROOT,LOGS+'/initialized-control.log');probe.parent.mkdir(parents=True,exist_ok=True)
    require_remaining(int(start),step_started,90)
    with probe.open('xb') as stream:
        probe_returncode=bounded_child([sys.executable,'-B',str(ROOT/PACKAGE/'audit_probe.py'),'--initialized-only'],stream,90)
    need(probe_returncode==0,'initialized real readset control failed')
    output=inputs.safe_path(ROOT,OUT);need(not output.exists(),'single fresh DUT output')
    output.parent.mkdir(parents=True,exist_ok=True)
    # Keep the entire postseal outer limit plus 60 seconds for cleanup/receipts.
    require_remaining(int(start),step_started,3330+122+60)
    log=inputs.safe_path(ROOT,LOGS+'/actual-launch.log')
    with log.open('xb') as stream:
        result=subprocess.run([sys.executable,'-B',str(ROOT/PACKAGE/'launch.py'),'--actual',
            '--data','work/qwen2_live_qkv_inputs_m128/ci01','--reference',recipe.REFERENCE,'--out',str(output),
            '--reviewed-source-manifest',value['source_closure_sha256']],
            cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=False)
    main_returncode=result.returncode
    # Even a complete numerical rejection can retain a valid sealed diagnostic.
    # The child itself rejects incomplete seals, debts and any identity drift.
    require_remaining(int(start),step_started,122+60)
    postlog=inputs.safe_path(ROOT,LOGS+'/postseal-gate.log')
    with postlog.open('xb') as stream:
        post_returncode=bounded_child([sys.executable,'-B','-m',PACKAGE.replace('/','.')+'.gate_probe','--execute'],stream,122)
    need(post_returncode==0,'postseal gate diagnosis incomplete')
    need(main_returncode==0,'bounded diagnostic numeric acceptance failed')
    return 'ACTUAL_PROCESS_COMPLETED_REQUIRES_AGGREGATE'


def aggregate():
    value=authorize()
    from . import aggregate as summary
    result=summary.collect(execute=True,source_digest=value['source_closure_sha256'])
    path=inputs.safe_path(ROOT,SUMMARY)
    with path.open('x') as stream:
        json.dump(result,stream,sort_keys=True,allow_nan=False);stream.write('\n')
    return 'ALLOWLISTED_AGGREGATE_READY'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('admit','capture','actual','aggregate'))
    args=parser.parse_args(argv)
    try:print({'admit':admit,'capture':capture,'actual':actual,'aggregate':aggregate}[args.action]())
    except Exception:
        # Detailed diagnostics never reach public stdout or the aggregate artifact.
        try:
            path=inputs.safe_path(ROOT,LOGS+'/failure-'+args.action+'.log')
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('x') as stream:traceback.print_exc(file=stream)
        except Exception:pass
        print('PLATFORM_FULLBLOCK_STAGE_FAILED_LOCAL_DETAILS_ONLY');return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
