#!/usr/bin/env python3
"""Actual Host execution helpers. No input/oracle admission CLI is exposed."""
from pathlib import Path
import hashlib,json,math,subprocess,sys
from verify_host_bf16_v_fixture import verify
from pack_host_bf16_v_fixture import fixture_input_hashes
ROOT=Path(__file__).resolve().parents[3]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def parse_marker(text,prefix):
    rows=[x for x in text.splitlines() if x.startswith(prefix+' ')]
    if len(rows)!=1:raise ValueError('missing/duplicate '+prefix)
    return dict(x.split('=',1) for x in rows[0].split()[1:])

def pass_result(build,fixture,outputs,log):
    source=json.loads((fixture/'manifest.json').read_text());count=source['token_count']
    metrics=parse_marker(log.read_text(),'HOST_BF16_V_PASS')
    expected=dict(tokens=count,token_base=source['token_base'],checked_bf16=count*512,
        canonical_bit_differences=0,write_ack_bytes=count*1024,logical_matrix_engines=1,
        physical_matrix_slices=8,idma_instances=1,unchanged_guards=1)
    if any(int(metrics[k])!=v for k,v in expected.items()) or metrics['native_operator_gate']!='PASS':
        raise ValueError('incomplete production Host numerical/ACK/guard coverage')
    for key,limit in (('native_max_abs',0.03125),('native_mean_abs',0.005)):
        if not math.isfinite(float(metrics[key])) or not 0<=float(metrics[key])<=limit:
            raise ValueError('unchanged native V operator threshold failed')
    actual=(outputs/'actual.bf16le').read_bytes();reference=(outputs/'reference.bf16le').read_bytes()
    if actual!=reference or len(actual)!=count*1024:raise ValueError('canonical output bytes differ')
    return dict(metrics=metrics,input_sha256=fixture_input_hashes(fixture,source),
        actual_sha256=hashlib.sha256(actual).hexdigest(),reference_sha256=hashlib.sha256(reference).hexdigest(),
        native_reference_sha256=source['files']['native_v.bf16le']['sha256'],
        fixture_sha256=sha(fixture/'manifest.json'),log_sha256=sha(log))

def verify_all_build_sources(build,log_name='final_source_verify.log'):
    build=Path(build);ready=json.loads((build/'build_ready.json').read_text())
    with (build/log_name).open('w') as log:
        subprocess.run([sys.executable,str(ROOT/'chisel/continuous_prefill/scripts/production_source_identity.py'),
            'verify',str(ROOT),str(build),ready['hardfloat_source']],stdout=log,stderr=subprocess.STDOUT,check=True)

def run_representative(build:Path,fixture:Path,session):
    """Only called by the live fresh wrapper; build-only never grants a PASS."""
    build,fixture=Path(build),Path(fixture)
    admitted=verify(fixture,session=session)
    ready=json.loads((build/'build_ready.json').read_text())
    if ready['status']!='BUILT_HOST_V_ONLY_NOT_NUMERICAL_PASS' or ready['numerical_pass'] is not False:
        raise ValueError('expected build-only receipt, not numerical acceptance')
    exe=build/'obj/VHostBlockTop';rtl=build/'generated/HostBlockTop.sv'
    identity={str(exe):sha(exe),str(rtl):sha(rtl)}
    if identity[str(exe)]!=ready['binary_sha256'] or identity[str(rtl)]!=ready['rtl_sha256']:
        raise ValueError('built DUT changed')
    faults={}
    for mode in ('pass','last-write-error','activation-read-error'):
        with (build/(mode+'.log')).open('w') as log:
            result=subprocess.run([str(exe),str(fixture),str(build/mode),mode],
                stdout=log,stderr=subprocess.STDOUT,timeout=1800)
        (build/(mode+'.exit')).write_text(str(result.returncode)+'\n')
        if result.returncode:raise RuntimeError('production Host execution failed: '+mode)
        if mode!='pass':
            fields=parse_marker((build/(mode+'.log')).read_text(),'HOST_BF16_V_FAULT_PASS')
            if fields['mode']!=mode or fields['status']!='3' or fields['published_bytes']!='0':
                raise ValueError('fault lifecycle evidence drift')
            ack=int(fields['write_ack_bytes'])
            if not 0<=ack<admitted['token_count']*1024 or (mode=='activation-read-error' and ack!=0):
                raise ValueError('fault ACK lifecycle drift')
            faults[mode]=fields
    numerical=pass_result(build,fixture,build/'pass',build/'pass.log')
    verify(fixture,session=session)
    if any(sha(Path(p))!=digest for p,digest in identity.items()):raise ValueError('DUT changed during execution')
    verify_all_build_sources(build)
    metrics=numerical['metrics']
    report=dict(status='PASS_PRODUCTION_HOST_V_ONLY',token_count=admitted['token_count'],token_base=admitted['token_base'],
        variant=admitted['variant'],phase=admitted['phase'],canonical_bit_differences=0,native_operator_gate_pass=True,
        native_bit_differences=int(metrics['native_bit_differences']),native_max_abs=float(metrics['native_max_abs']),
        native_mean_abs=float(metrics['native_mean_abs']),binary_sha256=identity[str(exe)],rtl_sha256=identity[str(rtl)],
        source_immutability_verified=True,initial_verilation_exit=ready['initial_verilation_exit'],
        experimental_default_off=True,q_k_supported=False,full_block_supported=False,
        actual_host_root=True,logical_matrix_engines=1,physical_matrix_slices=8,pinned_idma_instances=1,
        faults=faults,**numerical,**session.evidence())
    (build/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
