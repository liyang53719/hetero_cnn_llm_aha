"""Offline evidence assembly; no projection arithmetic or native forward."""
import json
import hashlib
import subprocess
from pathlib import Path
import numpy as np
from .run_reference import ROOT, SOURCE, PAYLOAD, record, sha, dump, MANIFEST_SHA, compare
from candidates.qwen35_35b_payload.packer import load_payload


REPORT_PINS = {
    16: ('c656f89bae36a1daddd0fa670eb1dd74c0bb9d229cc160ed7d7ee7c367fb9c8c',
         'aec6c6d278d5702993e9854079a229f85308286e4537f3ec0d6deb931933118d'),
    128: ('f68790a40c0a34761590b6a9d0cf0d69f400b138f2dafdb8c4d94f2f74542d4a',
          'e1831a1b36c58ed13c4046930aa4d060fab3c89965106e528ce85717954f9e1b')}
KN_SHA = '7fe59470202f20e4caefc14f276a74da18a7fd65fb869afb01783b31c3d3a213'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def verified_bytes(path, spec):
    """Hash the exact bytes returned to the caller before interpreting them."""
    path=Path(path).resolve()
    require(str(path)==spec['path'],'recorded output path changed')
    raw=path.read_bytes()
    require(len(raw)==spec['bytes'],'recorded output byte count changed')
    require(hashlib.sha256(raw).hexdigest()==spec['sha256'],'recorded output SHA256 changed')
    return raw


def verified_bf16(path, spec, m):
    raw=verified_bytes(path,spec)
    require(len(raw)==m*8192*2,'full QKV output shape changed')
    return np.frombuffer(raw,dtype='<u2').reshape(m,8192)


def require_joint_gate(result):
    require(result['overall_gate_pass'] and result['gate_pass'] and
            set(result['per_segment_original_gate'])=={'q','k','v'} and
            all(result['per_segment_original_gate'].values()),
            'whole output and each Q/K/V original gate must pass')


def pinned_report(path, digest):
    raw=Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==digest,'historical report SHA256 changed')
    return json.loads(raw)


def main():
    out=ROOT/'work/qwen35_35b_projection_reference_20261013T0535'
    result=dict(scope='OFFICIAL_FULL_SHAPE_OPERATOR_PROFILE_DIAGNOSTIC_ONLY',
        thresholds=dict(max_abs=0.03125,mean_abs=0.005),cases={},
        source_files={str(p.relative_to(ROOT)):sha(p) for p in SOURCE.glob('*.py')},
        source_c=record(SOURCE/'reference.c'),
        upstream_sources=json.loads((out/'upstream/verified_manifest.json').read_text()),
        guard_ast_comparison=json.loads((out/'guard_ast_comparison.json').read_text()),
        optimized_guard_negative=json.loads((out/'optimized_negative.json').read_text()),
        review_revalidation=dict(kind='READ_ONLY_RECOMPARISON_OF_HASH_VERIFIED_OUTPUT_BYTES',
            native_or_c_projection_rerun=False,arithmetic_source_changed=False,
            original_execution_source=record(out/'prereview_source/run_reference.py'),
            prior_evidence=record(out/'prereview_source/evidence.json'),
            prior_manifest=record(out/'prereview_source/source_manifest.json'),
            comparison_source=record(SOURCE/'run_reference.py'),
            finalization_source=record(SOURCE/'finalize.py')))
    for m in (16,128):
        path=out/f'hardened_m{m}'
        report=pinned_report(path/'report.json',REPORT_PINS[m][0])
        old=pinned_report(out/f'm{m}'/'report.json',REPORT_PINS[m][1])
        for source,digest in report['source_frozen'].items():
            selected=(out/'prereview_source/run_reference.py') if Path(source)==SOURCE/'run_reference.py' else Path(source)
            require(sha(selected)==digest,'executed source snapshot changed')
        native=verified_bf16(path/'official_output.bf16le',report['official_output'],m)
        old_native=verified_bf16(out/f'm{m}'/'official_output.bf16le',old['official_output'],m)
        require(np.array_equal(native,old_native),'hardening changed native output bytes')
        expected=(native.astype(np.uint32)<<16).view(np.float32).astype(np.float64)
        details={}
        for name,r in report['results'].items():
            actual=verified_bf16(path/(name+'.bf16le'),r['output'],m)
            old_actual=verified_bf16(out/f'm{m}'/(name+'.bf16le'),old['results'][name]['output'],m)
            require(np.array_equal(actual,old_actual),'hardening changed arithmetic output bytes')
            verified_bytes(path/(name+'.fp32le'),r['pre_bf16'])
            verified_bytes(out/f'm{m}'/(name+'.fp32le'),old['results'][name]['pre_bf16'])
            value=(actual.astype(np.uint32)<<16).view(np.float32).astype(np.float64)
            bad=actual!=native
            q=compare(actual,native,np)
            if name=='pair_hi_first_two_k1024':require_joint_gate(q)
            q.update({k:r[k] for k in ('intermediate_fp32_subnormal_observations',
                'libm_fmaf_calls','merge_fp32_add_calls','output','pre_bf16','seconds')})
            q['numerical_metrics_recomputed_from_current_verified_bytes']=True
            q['operation_counts_and_seconds_provenance']='Historical execution receipt; no arithmetic rerun'
            q['diagnostic_magnitude_cutoff']=1e-30
            q['diagnostic_cutoff_is_not_acceptance_gate']=True
            q['mismatches_with_output_magnitude_at_least_cutoff']=int(np.count_nonzero(bad&(np.maximum(np.abs(value),np.abs(expected))>=1e-30)))
            q['mismatches_with_abs_error_at_least_cutoff']=int(np.count_nonzero(bad&(np.abs(value-expected)>=1e-30)))
            q['mismatches_both_bf16_normal']=int(np.count_nonzero(bad&((actual&0x7f80)!=0)&((native&0x7f80)!=0)))
            q['max_mismatch_output_magnitude']=float(np.max(np.maximum(np.abs(value[bad]),np.abs(expected[bad])))) if bad.any() else 0.0
            details[name]=q
        log=(path/'run.log').read_text()
        primitive=[s for s in log.splitlines() if 'primitive,exec,cpu,matmul,' in s]
        require(len(primitive)==1 and f'{m}x2048:2048x8192' in primitive[0] and 'avx512_core_bf16' in primitive[0],'actual backend trace missing')
        kernels=[]
        for p in sorted(path.glob('dnnl*.bin')):
            text=subprocess.check_output(['objdump','-D','-b','binary','-m','i386:x86-64',str(p)],text=True)
            require(p.with_suffix('.asm').read_text()==text,'stored kernel disassembly changed')
            kernels.append(dict(**record(p),disassembly=record(p.with_suffix('.asm')),
                vdpbf16ps_instructions=text.count('vdpbf16ps'),vaddps_instructions=text.count('vaddps'),
                vcvtneps2bf16_instructions=text.count('vcvtneps2bf16')))
        require(sum(k['vdpbf16ps_instructions'] for k in kernels)>0,'native kernel instruction missing')
        result['cases'][str(m)]=dict(report=record(path/'report.json'),first_run_report=record(out/f'm{m}'/'report.json'),
            official_output=report['official_output'],input=report['input'],results=details,
            source_frozen=report['source_frozen'],original_and_hardened_outputs_identical=True,
            output_bytes_rehashed_before_comparison=True,
            native_primitive=primitive[0],native_kernel_artifacts=kernels,
            resource_ledger=report['resource_ledger'],runtime=report['runtime'],
            input_domain=report['input_domain'],weight_domain=report['weight_domain'],
            peak_rss_bytes=report['peak_rss_bytes'],numeric_seconds=report['total_numeric_seconds'])
    manifest,values=load_payload(ROOT,PAYLOAD,manifest_sha256=MANIFEST_SHA,include_qkv=True)
    raw=values['layers.0.linear_attn.in_proj_qkv.weight']
    p=out/'weights_kn.bf16le';kn=p.read_bytes()
    require(hashlib.sha256(kn).hexdigest()==KN_SHA and len(kn)==33554432,'materialized KN weights changed')
    require(np.array_equal(np.frombuffer(raw,dtype='<u2').reshape(8192,2048),np.frombuffer(kn,dtype='<u2').reshape(2048,8192).T),'NK-to-KN bits changed')
    result['weight_materialization']=dict(original_nk=record(PAYLOAD/'layers.0.linear_attn.in_proj_qkv.weight.bin'),
        derived_kn=record(p),mapping='KN[k,n] = NK[n,k], all 16,777,216 uint16 words compared',
        arithmetic_or_rounding=False,all_original_words_bitexact=True)
    result['domain_interpretation']=dict(
        libm_reference='FE_TONEAREST, FTZ=0, DAZ=0, gradual FP32 underflow and gradual BF16 RNE; tiny boundary tests reject incompatible host environment.',
        native='Actual dumped kernels use VDPBF16PS and VCVTNEPS2BF16. Intel documents instruction-local denormal flushing regardless of MXCSR. A clear MXCSR FTZ/DAZ therefore does not prove native gradual underflow.',
        inference='Observed tiny-only pair differences are consistent with the documented instruction-local underflow behavior. This diagnostic did not emulate flushing or prove a universal native backend equivalence.',
        manual_url='https://www.intel.com/content/dam/develop/external/us/en/documents/architecture-instruction-set-extensions-programming-reference-737410.pdf',
        manual_sections=['VCVTNEPS2BF16 pp.2-17/2-18 (PDF74/75)','VDPBF16PS pp.2-19/2-20 (PDF76/77)'])
    accepted=all(c['results']['pair_hi_first_two_k1024']['gate_pass'] and
                 all(c['results']['pair_hi_first_two_k1024']['per_segment_original_gate'].values())
                 for c in result['cases'].values())
    require(accepted and set(result['cases'])=={'16','128'},'missing or failed full-shape Q/K/V gates')
    result['claim_boundary']=dict(full_native_forward=False,actual_projection_owner_executed=False,rtl_executed=False,
        hardware_profile_admitted=False,bitexact_native_profile=False,
        empirical_full_shape_original_gates_pass=accepted,
        scope='Only M16 and M128 original L0 RMS outputs and complete official L0 QKV weight at pinned revisions; no universal input/backend claim.')
    dump(SOURCE/'evidence.json',result)
    print(json.dumps(dict(status='PASS_EVIDENCE_ASSEMBLY',evidence=record(SOURCE/'evidence.json'),
        derived_kn=result['weight_materialization']['derived_kn'],
        cases={m:{name:{k:r[k] for k in ('bit_mismatches','max_abs','mean_abs','mismatches_with_output_magnitude_at_least_cutoff','segments')} for name,r in c['results'].items()} for m,c in result['cases'].items()})),flush=True)


if __name__=='__main__':main()
