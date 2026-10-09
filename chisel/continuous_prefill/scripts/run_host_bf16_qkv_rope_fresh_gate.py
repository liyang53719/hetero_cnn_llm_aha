#!/usr/bin/env python3
"""Fresh M1 production QKV/Norm256/partial64 RoPE, with persistent CI execution.

One live official capture and independent integer/C reference authority feeds
packing, admission and the actual seven-command DUT. No saved tensor input,
external expected output or trust-digest CLI exists. Only two compact JSON
files may be uploaded. This gate does not execute attention, FFN or M128.
"""
from pathlib import Path
import argparse
import contextlib
import json
import os
import subprocess
import time

from pack_host_bf16_v_fixture import ROOT, rebuild_session
from host_bf16_qkv_reference import generate_projection_references
from host_bf16_qk_rope_reference import generate_attention_references
from host_bf16_qkv_rope_fixture import pack, verify, SOURCES
from host_bf16_qkv_rope_execution import BUILD_STATUS, MODES, run_case
from host_bf16_qkv_execution import verify_all_build_sources
from run_host_bf16_qkv_fresh_gate import require, sha, merge_sources, verify_checkout
from run_host_bf16_v_fresh_gate import _write_compact, _native_failure_evidence, _preflight, _git_head

SCRIPT_DIR = ROOT / 'chisel/continuous_prefill/scripts'
SCOPE = 'QKV_NORM256_PARTIAL64_COMMAND_SUBCHAIN'
ENTRY_SOURCES = SOURCES + (
    '.github/workflows/host-bf16-qkv-rope.yml', 'pyproject.toml',
    'chisel/continuous_prefill/scripts/run_host_bf16_qkv_rope_fresh_gate.py',
    'chisel/continuous_prefill/scripts/run_host_bf16_qkv_rope_gate.sh',
    'chisel/continuous_prefill/scripts/host_bf16_qk_rope_reference.py',
    'chisel/continuous_prefill/scripts/host_bf16_qkv_reference.py',
    'chisel/continuous_prefill/scripts/run_host_bf16_qkv_fresh_gate.py',
    'chisel/continuous_prefill/scripts/run_host_bf16_v_fresh_gate.py',
    'chisel/continuous_prefill/scripts/pack_host_bf16_v_fixture.py',
)


def case_plan():
    return [('cold0', mode) for mode in MODES] + [('carried127', 'pass')]


def run(args):
    original = Path(args.output)
    require(not original.is_symlink(), 'output symlink')
    out = original.resolve()
    require(out.is_relative_to(ROOT/'work') and out != ROOT/'work' and not out.exists(),
            'new output beneath ignored work required')
    out.mkdir(parents=True)
    hashes = dict(source_sha256={}, input_sha256={}, output_sha256={})
    summary = dict(status='RUNNING_FRESH_HOST_QKV_NORM_ROPE_M1', stage='preflight',
        numerical_acceptance=False, scope=SCOPE, actual_host_root=True, experimental_default_off=True,
        representative_tokens=1, max_declared_rows=128, full128_executed=False,
        attention_supported=False, ffn_supported=False, full_block_supported=False,
        logical_matrix_engines=1, physical_matrix_slices=8, pinned_idma_instances=1,
        scalar_service_shared=True, frozen_norm_recipe='C1', frozen_rope_recipe='B1',
        cross_host_byte_equivalence_claimed=False, fresh_official_executions=None,
        reused_official_executions=0, planned_actual_invocations=len(case_plan()), cases=[],
        artifact_upload_allowlist=['compact/summary.json','compact/source_input_hashes.json'])
    started = time.monotonic()
    deadline = started + 9000

    def remaining(cap):
        seconds=int(deadline-time.monotonic()-120)
        require(seconds>0,'runner total budget exhausted; preserve failure artifact before workflow hard timeout')
        return min(cap,seconds)
    session = references = attention = None
    build = out/'host_build'

    def checkpoint(stage):
        summary.update(stage=stage, elapsed_seconds=time.monotonic()-started,
                       runner_budget_seconds=9000,remaining_budget_seconds=max(0,int(deadline-time.monotonic())))
        _write_compact(out, summary, hashes)

    try:
        merge_sources(hashes['source_sha256'], {name:sha(ROOT/name) for name in ENTRY_SOURCES})
        head = _git_head();summary['git_head'] = head
        verify_checkout(head, hashes['source_sha256'])
        env = os.environ.copy();env.setdefault('BUILD_JOBS','1')
        require(env['BUILD_JOBS']=='1', 'serial build required')
        env['SOURCE_IDENTITY_SCOPE']='full'
        summary['idma_preflight']=_preflight(env,out)
        checkpoint('fresh_official_prefix_capture')
        with (out/'pipeline.log').open('w') as log, contextlib.redirect_stdout(log):
            session = rebuild_session(out/'official_capture', args.payload_layer0,
                                      args.payload_layer3, args.payload_extra)
            summary.update(session.evidence())
            require(session.fresh and summary['fresh_official_executions']==2 and
                    summary['reused_official_executions']==0, 'fresh capture required')
            hashes['official_capture_manifest_sha256']=session.manifest_sha256
            merge_sources(hashes['source_sha256'],session.verify()['source_sha256'])
            summary['native_full_block_failures']=_native_failure_evidence(session)
            checkpoint('fresh_baseline_integer_c_projection_reference')
            references=generate_projection_references(session,out/'projection_reference',variants=('baseline',))
            receipt=references.verify(session=session)
            require(receipt['head_jobs']==24 and receipt['matrix_accumulator_steps']==10485760,
                    'two M1 full Q8/K2/V2 reference inventory')
            require(receipt['native_operator_gate_pass'] is True,'unchanged native projection operator gate failed')
            merge_sources(hashes['source_sha256'],receipt['source_sha256'])
            hashes['projection_reference_receipt_sha256']=references.receipt_sha256
            summary['projection_reference']={key:receipt[key] for key in (
                'status','origin','head_jobs','matrix_accumulator_steps','native_operator_gate_pass',
                'native_thresholds','full128_reference_generated','cross_variant_input_identity_assumed')}
            checkpoint('fresh_frozen_norm_rope_integer_c_reference')
            attention=generate_attention_references(session,references,out/'attention_reference',variants=('baseline',))
            attention_receipt=attention.verify(session=session,reference_session=references)
            hashes['attention_reference_receipt_sha256']=attention.receipt_sha256
            merge_sources(hashes['source_sha256'],attention_receipt['source_sha256'])
            summary['attention_reference']=attention_receipt
            require(attention_receipt['original_operator_gate_pass'] is True,
                    'frozen Norm/RoPE native operator gate failed; original limits retained')
            verify_checkout(head,hashes['source_sha256'])
            checkpoint('production_host_build_only')
            with (out/'host_build.log').open('w') as log:
                subprocess.run(['bash',str(SCRIPT_DIR/'run_host_bf16_qkv_rope_gate.sh'),str(build),'0'],
                    cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=remaining(7200))
            ready=json.loads((build/'build_ready.json').read_text())
            require(ready['status']==BUILD_STATUS and ready['numerical_pass'] is False and
                    ready['initial_verilation_exit']==0,'build-only receipt')
            merge_sources(hashes['source_sha256'],json.loads((build/'sources.sha256.json').read_text()))
            summary['build']=ready;summary['toolchain']=json.loads((build/'toolchain.json').read_text())
            hashes.update(binary_sha256=ready['binary_sha256'],rtl_sha256=ready['rtl_sha256'],
                          build_ready_sha256=sha(build/'build_ready.json'))
            fixtures={}
            for case,mode in case_plan():
                label=case+'_'+mode.replace('-','_');checkpoint('actual_host_'+label)
                authority=dict(session=session,reference_session=references,attention_reference_session=attention)
                if case not in fixtures:
                    fixture=out/(case+'_fixture');pack(fixture,case,**authority)
                    admitted=verify(fixture,**authority)
                    require(type(admitted.get('input_sha256')) is dict and admitted['input_sha256'],'missing admitted input identity')
                    hashes['input_sha256'][case]=admitted['input_sha256']
                    fixtures[case]=fixture
                result=run_case(build,fixtures[case],mode,label=label,timeout_seconds=remaining(3600),**authority)
                require(result['status']=='PASS_PRODUCTION_HOST_QKV_QKNORM_ROPE_CASE' and
                        result['actual_dut_identity_verified'] is True and
                        result['binary_sha256']==hashes['binary_sha256'] and
                        result['rtl_sha256']==hashes['rtl_sha256'],'case DUT identity drift')
                summary['cases'].append(dict(name=label,case=case,mode=mode,result=result))
                require(len(result['runs'])==(2 if mode=='reset-recovery' else 1),'run inventory mismatch')
                hashes['output_sha256'][label]={str(index):row['actual_sha256'] for index,row in enumerate(result['runs'])}
                require(all(type(value) is dict and value for value in hashes['output_sha256'][label].values()),'missing actual output identity')
                checkpoint('completed_'+label)
            checkpoint('final_identity_verification')
            references.verify(session=session);attention.verify(session=session,reference_session=references)
            verify_all_build_sources(build,'fresh_final_source_verify.log')
            require(sha(build/'obj/VHostBlockTop')==hashes['binary_sha256'] and
                    sha(build/'generated/HostBlockTop.sv')==hashes['rtl_sha256'] and
                    sha(build/'build_ready.json')==hashes['build_ready_sha256'],'DUT identity changed')
            verify_checkout(head,hashes['source_sha256'])
            summary.update(session.evidence())
            summary['native_full_block_failures']=_native_failure_evidence(session)
            require(len(summary['cases'])==len(case_plan()),'incomplete actual case inventory')
            summary.update(status='PASS_FRESH_HOST_QKV_NORM_ROPE_M1',numerical_acceptance=True,
                           git_head_verified_unchanged=True,source_immutability_verified=True)
            checkpoint('complete')
        return summary,0
    except (Exception,KeyboardInterrupt) as error:
        summary.update(status='FAIL_FRESH_HOST_QKV_NORM_ROPE_M1',numerical_acceptance=False,
                       error=dict(type=type(error).__name__,message=str(error)))
        if session is not None:
            try:
                summary.update(session.evidence());summary['native_full_block_failures']=_native_failure_evidence(session)
            except Exception as drift:summary['final_capture_verification_error']=str(drift)
        candidates=[out/'host_build.log',out/'pipeline.log']
        if build.is_dir(): candidates += list(build.glob('*.log'))
        latest=sorted((p for p in candidates if p.is_file() and not p.is_symlink()),key=lambda p:p.stat().st_mtime)[-4:]
        summary['diagnostic_log_tail']={str(p.relative_to(out)):p.read_text(errors='replace')[-12000:] for p in latest}
        checkpoint(summary['stage'])
        return summary,1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    for name,default in (('layer0','qwen35_layer0_payload'),('layer3','qwen35_layer3_payload'),('extra','qwen35_prefix_payload')):
        parser.add_argument('--payload-'+name,type=Path,default=ROOT/'work'/default)
    args=parser.parse_args()
    try:summary,code=run(args)
    except (ValueError,OSError) as error:
        print(json.dumps(dict(status='HOST_QKV_NORM_ROPE_ENTRY_REJECTED',error=str(error))));raise SystemExit(2)
    print(json.dumps(summary,sort_keys=True,separators=(',',':')));raise SystemExit(code)

if __name__=='__main__':main()
