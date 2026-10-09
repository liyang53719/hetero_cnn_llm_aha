#!/usr/bin/env python3
"""Generate the identical frozen full top and inspect concat calls; never run it."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from run_profile import (PIN, RTL_SHA256, HERE, DIAGNOSTIC_ROOT, require, sha, git,
                         checked_paths, imports, frozen_file, relocated_builder,
                         source_environment, finalize_supervision)

BUDGET_SECONDS = 1200
BUILD_STOP = 'python3 "$P/scripts/build_host_hierarchy_bounded.py" "$OUT" --reserve-bytes "${BUILD_RESERVE_BYTES:-1073741824}" >"$OUT/make.log" 2>&1'
POST_CODEGEN_CHECKS = 'python3 "$P/scripts/host_bf16_v_toolchain.py" after "$OUT"\nrecord_verilator_elf "$OUT/actual_verilator_after.json"\ncmp "$OUT/actual_verilator_before.json" "$OUT/actual_verilator_after.json"\npython3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" >"$OUT/build_source_verification.log"\n'
EXPECTED_CPP = {
    'obj/VHostBlockTop___024root__DepSet_h74254c49__13.cpp': '8c97e4003108d2ff4dc356546d4ddfa922cfbd3968293ba7ca3df27bfa0d06f8',
    'obj/VHostBlockTop___024root__DepSet_h74254c49__94.cpp': 'f1b680a5fb3ff465a4a8885e7e3c8c0da4a049fa12ae4c07fe4ba79a4c90b87f',
}


def codegen_builder(raw, source):
    """Keep the exact emit/verilation argv and stop before the C++ builder."""
    driver = source/'chisel/continuous_prefill/tests/host_bf16_attention_core.cpp'
    text = relocated_builder(raw, source, driver)
    require(text.count(BUILD_STOP) == 1, 'frozen C++ build boundary changed')
    prefix = text.split(BUILD_STOP, 1)[0]
    require(prefix.count('hier_verilation >"$OUT/hierarchy_verilation.log" 2>&1') == 1,
            'missing original final child/top Verilation stage')
    require(text.count(POST_CODEGEN_CHECKS) == 1, 'original read-only post-generation checks changed')
    return prefix + POST_CODEGEN_CHECKS + 'echo CODEGEN_ONLY_STOP_BEFORE_CPP_BUILD\nexit 0\n'


def args():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    return p.parse_args()


def run_worker(a):
    source,out=checked_paths(a); frozen=imports(source);out.mkdir(parents=True)
    from run_host_bf16_v_fresh_gate import _write_compact
    from concat_inventory import collect
    diagnostic=git(DIAGNOSTIC_ROOT,'rev-parse','HEAD')
    env=source_environment(os.environ,diagnostic,PIN)
    os.environ['GITHUB_SHA']=PIN
    os.environ['ATTENTION_PROFILE_DIAGNOSTIC_SHA']=diagnostic
    env['BUILD_JOBS']='1'
    started=time.monotonic()
    summary=dict(schema='ATTENTION_WIDE_CONCAT_CODEGEN_V1',status='RUNNING_CODEGEN_ONLY',
        stage='preflight',production_source_commit=PIN,diagnostic_source_commit=diagnostic,
        numerical_acceptance=False,functional_rtl_changed=False,hierarchy_changed=False,
        model_capture_executions=0,reference_executions=0,cpp_compilation_performed=False,
        rtl_simulation_executions=0,budget_seconds=BUDGET_SECONDS,
        artifact_upload_allowlist=['compact/summary.json','compact/source_input_hashes.json','selected-source/**'])
    hashes=dict(source_sha256={},diagnostic_source_sha256={},input_sha256={},output_sha256={})
    def checkpoint(stage):
        summary.update(stage=stage,elapsed_seconds=time.monotonic()-started)
        _write_compact(out,summary,hashes)
    build=out/'host_build'
    try:
        with frozen.total_budget(BUDGET_SECONDS-60):
            for p in sorted(x for x in HERE.iterdir() if x.is_file())+[DIAGNOSTIC_ROOT/'.github/workflows/attention-top-profile.yml']:
                name=str(p.relative_to(DIAGNOSTIC_ROOT))
                require(p.read_bytes()==subprocess.check_output(['git','-C',str(DIAGNOSTIC_ROOT),'show','HEAD:'+name]),
                        'diagnostic source drift: '+name)
                hashes['diagnostic_source_sha256'][name]=sha(p)
            summary['idma_preflight']=frozen._preflight(env,out)
            raw=frozen_file(source,'chisel/continuous_prefill/scripts/run_host_bf16_attention_core_gate.sh')
            builder=out/'codegen_only.sh';builder.write_text(codegen_builder(raw,source))
            hashes['builder_sha256']=sha(builder);hashes['original_builder_sha256']=hashlib.sha256(raw).hexdigest()
            checkpoint('exact_emit_and_hierarchy_codegen')
            with (out/'codegen.log').open('w') as log:
                subprocess.run(['bash',str(builder),str(build),'0'],cwd=source,env=env,
                               stdout=log,stderr=subprocess.STDOUT,check=True,timeout=BUDGET_SECONDS-120)
            require(sha(builder)==hashes['builder_sha256'],'codegen builder changed')
            require(sha(build/'generated/HostBlockTop.sv')==RTL_SHA256,'original exact RTL SHA mismatch')
            forbidden=[p for p in build.rglob('*') if p.is_file() and
                       (p.suffix in ('.o','.a','.gch') or p.name=='VHostBlockTop')]
            summary['cpp_compilation_artifacts_found']=[str(p.relative_to(build)) for p in forbidden]
            if forbidden:summary['cpp_compilation_performed']=True
            require(not forbidden,'C++ compilation artifacts found during codegen-only stage')
            hashes['source_sha256']=json.loads((build/'sources.sha256.json').read_text())
            frozen.verify_checkout(PIN,hashes['source_sha256'])
            summary['generated_rtl_admission']=json.loads((build/'generated_rtl_identity.json').read_text())
            summary['actual_verilator']=json.loads((build/'actual_verilator_after.json').read_text())
            require(summary['actual_verilator']==json.loads((build/'actual_verilator_before.json').read_text()),
                    'actual Verilator changed during generation')
            summary['toolchain']=json.loads((build/'toolchain.json').read_text())
            summary['source_and_hardfloat_final_verify']=(build/'build_source_verification.log').read_text().strip()
            require(summary['source_and_hardfloat_final_verify']=='SOURCE_IMMUTABILITY_PASS',
                    'full source/HardFloat immutability check absent')
            hashes['compiler_jars_sha256']=sha(build/'compiler_jars.sha256.json')
            hashes['hardfloat_manifest_sha256']=sha(build/'hardfloat.sha256.json')
            hashes['rtl_sha256']=sha(build/'generated/HostBlockTop.sv')
            # These are the actual generated caller files sampled in run37982064254.
            summary['sampled_cpp_identity']={name:dict(expected_sha256=digest,actual_sha256=sha(build/name),
                exact_match=sha(build/name)==digest) for name,digest in EXPECTED_CPP.items()}
            checkpoint('collect_concat_callers')
            summary['concat_inventory']=collect(build,out/'selected-source')
            require(summary['concat_inventory']['required_source_complete'] is True,
                    'required sampled caller/header/runtime source was not preserved')
            require(all(row['exact_match'] for row in summary['sampled_cpp_identity'].values()),
                    'regenerated sampled C++ caller source differs; inspect preserved source before attribution')
            frozen.verify_checkout(PIN,hashes['source_sha256'])
            hashes['selected_source_sha256']={str(p.relative_to(out)):sha(p)
                for p in sorted((out/'selected-source').rglob('*')) if p.is_file()}
            require(all(sha(DIAGNOSTIC_ROOT/name)==digest for name,digest in hashes['diagnostic_source_sha256'].items()),
                    'final diagnostic source drift')
            summary['status']='COMPLETE_CODEGEN_ONLY_NO_NUMERICAL_ACCEPTANCE'
            checkpoint('complete');return 0
    except (Exception,KeyboardInterrupt) as error:
        summary.update(status='INCOMPLETE_CODEGEN_ONLY',error=dict(type=type(error).__name__,message=str(error)))
        summary['diagnostic_log_tail']={str(p.relative_to(out)):p.read_text(errors='replace')[-4000:]
            for p in [out/'codegen.log',build/'compile_emit.log',build/'hierarchy_verilation.log'] if p.is_file()}
        if (build/'generated_rtl_identity.json').is_file():
            summary['generated_rtl_admission']=json.loads((build/'generated_rtl_identity.json').read_text())
        checkpoint(summary['stage']);return 1


def worker_entry():
    signal.pthread_sigmask(signal.SIG_UNBLOCK,(signal.SIGINT,signal.SIGTERM))
    raise SystemExit(run_worker(args()))


def main():
    a=args();source,out=checked_paths(a);frozen=imports(source)
    command=[sys.executable,'-c','import sys;sys.path.insert(0,sys.argv.pop(1));from run_codegen import worker_entry;worker_entry()',
             str(HERE),'--source-root',str(source),'--output',str(out)]
    result=frozen.supervise_process(command,timeout_seconds=BUDGET_SECONDS)
    raise SystemExit(finalize_supervision(out,result))

if __name__=='__main__':main()
