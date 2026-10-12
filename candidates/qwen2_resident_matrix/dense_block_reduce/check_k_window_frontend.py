#!/usr/bin/env python3
"""Bounded actual Dense K-window owner CHIRRTL; no RTL/simulation/QoR claim.

Reuses a VERIFIED official_bf16 frontend source/dependency receipt, composes the
new patch in a fresh directory, and typechecks the complete existing source set.
The prepatch owner is renamed only for exact normalized disabled-IR comparison.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[2]
OWNER = 'candidates/qwen2_resident_matrix/transposed_owner/TransposedDenseOwner.scala'
PROFILES = ('parent_default', 'disabled_default', 'parent_official', 'disabled_official',
            'enabled_official', 'enabled_burst')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


def run(baseline, out, compose_only=False):
    if out.exists():
        raise ValueError('use a fresh evidence directory')
    parent = json.loads((baseline/'summary.json').read_text())
    if parent['status'] != 'PASS_OFFICIAL_BF16_TYPECHECK_AND_BOUNDED_FRONTEND_ONLY':
        raise ValueError('verified official frontend baseline required')
    for path, digest in parent['source_sha256'].items():
        if sha((baseline/path).read_bytes()) != digest:
            raise ValueError('baseline source drift: '+path)
    out.mkdir(parents=True)
    start = time.monotonic()
    report = dict(status='STARTED', baseline=str(baseline),
                  baseline_receipt_sha256=sha((baseline/'summary.json').read_bytes()),
                  commands=[], rtl_generated=False, hardware_arithmetic_executed=False,
                  full_top_elaborated=False, public_coordinator_integrated=False,
                  k_window_source_typechecked=False, model_is_cycle_equivalent=False)
    def save():
        (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    def command(argv, log):
        entry = dict(argv=argv, log=log, status='RUNNING')
        report['commands'].append(entry)
        save()
        with (out/log).open('w') as stream:
            result = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
        entry.update(exit_code=result.returncode, status='FINISHED')
        save()
        if result.returncode:
            raise RuntimeError('failed: '+log)
    try:
        source = out/'source'
        shutil.copytree(baseline/'source', source)
        original = (source/OWNER).read_text()
        body = original.split('class TransposedDenseDownOwner', 1)[1]
        body = 'class DenseKWindowParent'+body
        body = body.replace(' extends Module {', ' extends Module {\n  override def desiredName = "TransposedDenseDownOwner"', 1)
        base = source/'DenseKWindowParent.scala'
        base.write_text('package heteronpu.continuous\nimport chisel3._\nimport chisel3.util._\n'+body)
        patch = TASK/'k_window.patch'
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=source, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=source, check=True)
        front = source/'KWindowElaboration.scala'
        shutil.copyfile(TASK/'KWindowElaboration.scala', front)
        compile_argv = [x.replace(str(baseline), str(out)) for x in parent['commands'][0]['argv']]
        compile_argv += [str(base), str(front)]
        (out/'classes').mkdir()
        report['source_sha256'] = {str(p.relative_to(out)):sha(p.read_bytes()) for p in sorted(source.rglob('*.scala'))}
        report['tooling_sha256'] = {n:sha((TASK/n).read_bytes()) for n in ('k_window.patch', 'KWindowElaboration.scala', 'check_k_window_frontend.py')}
        report['compiler_argv'] = compile_argv
        if compose_only:
            report['status']='COMPOSED_ONLY'
            save()
            return report
        command(compile_argv, 'compile.log')
        report['k_window_source_typechecked'] = True
        cp = compile_argv[compile_argv.index('-cp')+1]
        java = ['java', '-Xmx1024m', '-XX:ActiveProcessorCount=1', '-cp', str(out/'classes')+':'+cp,
                'heteronpu.continuous.KWindowElaboration', str(out/'chirrtl')]
        for profile in PROFILES:
            command(java+[profile], profile+'.log')
        helper = module('k_window_ir_normalizer', ROOT/'scripts/check_matrix_interface_candidate.py')
        official = module('k_window_ir_inventory', TASK.parent/'official_bf16/check_frontend.py')
        registers = module('k_window_register_inventory', TASK.parent/'transposed_host/check_frontend.py')
        window = module('k_window_bank_audit', TASK.parent/'ffn_window/check_frontend.py')
        normalized = {p:official.normalized((out/'chirrtl'/(p+'.fir')).read_text(), helper) for p in PROFILES}
        report['default_off_ir'] = {}
        for policy in ('default', 'official'):
            before, after = normalized['parent_'+policy], normalized['disabled_'+policy]
            same = before == after
            report['default_off_ir'][policy] = dict(equal=same, before_sha256=sha(before.encode()), after_sha256=sha(after.encode()))
            if not same:
                import difflib
                (out/(policy+'_disabled.diff')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True))))
                raise ValueError('default-off IR drift: '+policy)
        report['resources'] = {}
        base_inv = official.resource_inventory(normalized['disabled_official'], registers)
        for profile in ('enabled_official', 'enabled_burst'):
            fir = normalized[profile]
            banks = window.memory_audit(fir, allow_operand_queue=True)
            inv = official.resource_inventory(fir, registers)
            current = inv['registers_by_module']['TransposedDenseDownOwner']
            old = base_inv['registers_by_module']['TransposedDenseDownOwner']
            if current['finalValue']['bits'] != 131072:
                raise ValueError('existing finalValue must stay one 16 KiB hold')
            if inv['instances_by_module'] != base_inv['instances_by_module']:
                raise ValueError('arithmetic or bank module duplication')
            if inv['memories_by_module'] != base_inv['memories_by_module']:
                raise ValueError('memory declaration or port change')
            delta = {k:v for k,v in current.items() if old.get(k) != v}
            if set(delta) != {'kPolicy'} or delta['kPolicy']['bits'] != 66:
                raise ValueError('unexpected payload/state added: '+str(delta))
            report['resources'][profile] = dict(banks=banks, metadata_added_bits=66,
                existing_final_value_bits=131072, new_payload_buffers=0, new_sram_arrays=0,
                new_matrix_units=0, register_delta=delta)
        report['status'] = 'PASS_K_WINDOW_OWNER_FRONTEND_ONLY'
    except Exception as exc:
        report['status']='FAILED'
        report['error']=str(exc)
        raise
    finally:
        report['wall_seconds']=time.monotonic()-start
        save()
    return report


if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--baseline', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--compose-only', action='store_true')
    args=ap.parse_args()
    print(run(args.baseline.resolve(), args.out.resolve(), args.compose_only)['status'])
