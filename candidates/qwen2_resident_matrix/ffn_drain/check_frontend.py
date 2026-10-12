#!/usr/bin/env python3
"""Pinned actual source typecheck and bounded independent Activation drain frontend.

No RTL, simulation, full Host/kernel elaboration, native arithmetic acceptance
or area/timing result. Public Host fusion remains a separate successor increment.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, re, subprocess, sys, time
sys.dont_write_bytecode = True
TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[2]
HOST = TASK.parent / 'transposed_host'
WINDOW = TASK.parent / 'ffn_window'
COMMIT = 'c761ec824ce2c027a66c22feb4a2154829f9d545'
PREFIX = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
OWNER = 'candidates/qwen2_resident_matrix/transposed_owner/'
PATCH = 'candidates/qwen2_resident_matrix/ffn_drain/drain.patch'
HARDFLOAT = 'c1105e6ac6a0dd90fc80893efc4830ab609005d3'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def frozen(path):
    return subprocess.check_output(['git', 'show', COMMIT + ':' + path], cwd=ROOT)


def compose(out):
    window = module('drain_window_compose', WINDOW / 'check_frontend.py')
    paths, pins = window.compose(out)
    if pins != json.loads((WINDOW / 'source_pins.json').read_text()):
        raise ValueError('unchanged FFN window composition identity drift')
    cls='TransposedDenseDownOwner'
    original=(out/(OWNER+'TransposedDenseOwner.scala')).read_text().split('class '+cls,1)[1]
    original=('class '+cls+original).replace('class '+cls, 'class '+cls+'WindowBaseline',1)
    original=original.replace(' extends Module {',' extends Module {\n  override def desiredName = "'+cls+'"',1)
    (out/'baseline'/(cls+'WindowBaseline.scala')).write_text('package heteronpu.continuous\nimport chisel3._\nimport chisel3.util._\n'+original)
    data=(ROOT/PATCH).read_bytes();patch=out/'patch_ffn_drain.patch';patch.write_bytes(data)
    subprocess.run(['git','apply','--check',str(patch)],cwd=out,check=True)
    subprocess.run(['git','apply',str(patch)],cwd=out,check=True)
    pins['patches'][PATCH]=sha(data)
    pins['patched_sources']={p:sha((out/p).read_bytes()) for p in paths}
    for name in ('check_frontend.py','source_pins.json','FfnWindowElaboration.scala'):
        path=WINDOW/name;pins['composition_helpers'][str(path.relative_to(ROOT))]=sha(path.read_bytes())
    return paths,pins


def normalized(fir, helper):
    # Chisel includes source locations inside assertion printf string literals
    # as well as @ annotations. Drop only diagnostic file/line locations;
    # preserve the complete assertion expression and all hardware statements.
    return re.sub(r'(?<= at )[A-Za-z_0-9]+\.scala:\d+ ', '<source> ', helper.normalized_chirrtl(fir))


def memory_audit(fir, allow_operand_queue=False):
    memories = re.findall(r'^\s*smem (\w+) : UInt<256>\s*\[(\d+)\]', fir, re.M)
    if len(memories) != 32 or sorted(int(n) for _, n in memories) != [160]*16+[1376]*16:
        raise ValueError('fixed 32 SRAM geometry drift')
    result = {}
    for name, depth in memories:
        ports = {kind: len(re.findall(r'^\s*'+kind+r' mport \w+ = '+name+r'\[', fir, re.M)) for kind in ('read', 'write')}
        if ports != {'read': 1, 'write': 1}:
            raise ValueError('physical bank port drift: '+name)
        result[name] = {'depth': int(depth), 'width': 256, **ports}
    extra = re.findall(r'^\s*cmem (\w+) : (.*) \[(\d+)\]', fir, re.M)
    expected = 33 if allow_operand_queue else 32
    if len(re.findall(r'^\s*(?:s|c)mem ', fir, re.M)) != expected:
        raise ValueError('hidden extra memory')
    if allow_operand_queue and (len(extra) != 1 or extra[0][0] != 'ram' or int(extra[0][2]) != 4):
        raise ValueError('preexisting four-entry operand queue drift')
    return result


def audit(directory, helper):
    window=module('drain_window_audit', WINDOW/'check_frontend.py')
    host=module('drain_register_helper', HOST/'check_frontend.py')
    report=window.audit(directory,helper)
    report.update(act_ddr_drain_implemented=True, host_ffn_dispatch_implemented=False,
        independent_activation_job=True, no_public_host_completion=True)
    report['window_on_drain_off_ir']={}
    for label,before,after in (('nonburst','owner_window_baseline','owner_enabled'),
                               ('burst','owner_window_burst_baseline','owner_window_burst_disabled')):
        old=normalized((directory/(before+'.fir')).read_text(),helper)
        new=normalized((directory/(after+'.fir')).read_text(),helper)
        if old!=new:raise ValueError('window-on/drain-off normalized CHIRRTL drift: '+label)
        if 'io_drain' in new or 'io_window_result_bits_cycles' in new:
            raise ValueError('drain-off ABI drift: '+label)
        report['window_on_drain_off_ir'][label]={'equal':True,'sha256':sha(new.encode())}
    report['drain_register_inventory']={}
    for profile in ('owner_drain','owner_drain_burst','owner_drain_only'):
        fir=normalized((directory/(profile+'.fir')).read_text(),helper)
        report['resource_audit'][profile]=memory_audit(fir,allow_operand_queue=True)
        if re.search(r'inst .* of (?:SiluVectorUnit|BlockScalarFloat|MatrixPipelineService)',fir):
            raise ValueError('drain added arithmetic resource')
        regs=host.register_inventory(fir)
        owner=regs['TransposedDenseDownOwner']
        for name,bits in (('finalValue',131072),('prefixWriteIndex',8),('writeRow',7),('writeContext',3),('writeBeat',1)):
            if owner[name]['bits']!=bits:raise ValueError('shared payload/cursor drift: '+name)
        baseline=host.register_inventory(normalized((directory/('owner_window_burst_disabled.fir' if profile=='owner_drain_burst' else 'owner_enabled.fir')).read_text(),helper))
        base=baseline['TransposedDenseDownOwner']
        additions={k:v for k,v in owner.items() if base.get(k)!=v}
        if any(v['bits']>=512 for v in additions.values()):
            raise ValueError('new drain payload register')
        report['drain_register_inventory'][profile]={'by_module':regs,'added_or_changed':additions,
            'metadata_added_bits':sum(v['bits'] for v in additions.values()),
            'net_owner_register_bits':sum(v['bits'] for v in owner.values())-sum(v['bits'] for v in base.values())}
    report['drain_storage_ledger']={'existing_final_value_bits':131072,'maximum_group_live_bytes':10240,
        'new_payload_buffers':0,'new_sram_arrays':0,'new_sfu_units':0,'new_matrix_units':0,
        'shared_write_row_bits':7,'shared_read_cursor_bits':8,'shared_row_beat_cursor_bits':4}
    report['drain_contract']={'fixed_slot':2,'rows':[16,128],'full_n':8960,'activation_input_k':8960,
        'cols':[32,64,96,128,160],'output':'FP32','packet_bytes':64,'full_mask':True,
        'burst_boundary_bytes':1024,'completion_after_release_verify':True,
        'read_count':'matching actual response.fire','ddr_bytes':'matching successful actual DDR ACK',
        'held_result':'immutable; later abort/late response gates publication through sticky resetRequired',
        'permissions':'QwenOwnerJob carries no permission bits; original Host checks remain required'}
    report['generated_chirrtl']={p.name:{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in sorted(directory.glob('*.fir'))}
    return report


def run(out, cache, hardfloat, validate_only=False):
    if out.exists():
        raise ValueError('use a new evidence directory')
    out.mkdir(parents=True)
    start = time.monotonic()
    report = {'status': 'STARTED', 'source_commit': COMMIT, 'ffn_window_parent_commit': 'c761ec824ce2c027a66c22feb4a2154829f9d545', 'commands': [],
              'tooling_sha256': {name:sha((TASK/name).read_bytes()) for name in ('check_frontend.py','test_frontend.py','source_pins.json','DrainElaboration.scala','drain.patch')},
              'full_host_top_typechecked': False, 'full_qwen_owner_kernel_typechecked': False,
              'top_elaborated': False, 'rtl_generated': False, 'hardware_arithmetic_executed': False,
              'java_budget': {'active_processors': 1, 'heap_mib': 1024, 'timeout_seconds_per_command': 180}}
    def save():
        (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    def command(argv, name):
        t = time.monotonic()
        entry = {'argv': argv, 'log': name, 'exit_code': None, 'status': 'RUNNING'}
        report['commands'].append(entry);save()
        with (out/name).open('w') as log:
            result = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        entry.update(exit_code=result.returncode, wall_seconds=time.monotonic()-t, status='FINISHED');save()
        if result.returncode:
            raise RuntimeError('command failed: '+name)
    try:
        source = out/'source';source.mkdir()
        paths, pins = compose(source)
        if pins != json.loads((TASK/'source_pins.json').read_text()):
            raise ValueError('frozen source/patch/postimage identity drift')
        report['source_pins'] = pins
        route = json.loads(frozen('candidates/qwen2_resident_matrix/transposed_route/manifest.json'))
        helper = module('ffn_frontend_helper', ROOT/'scripts/check_matrix_interface_candidate.py')
        if sha((ROOT/'scripts/check_matrix_interface_candidate.py').read_bytes()) != route['dependencies']['scripts/check_matrix_interface_candidate.py']:
            raise ValueError('dependency helper drift')
        lock_path = ROOT/'chisel/rope_hardware_oracle/maven-lock.json'
        if sha(lock_path.read_bytes()) != route['maven_lock_sha256']:
            raise ValueError('Maven lock drift')
        dependencies = helper.dependency_paths(json.loads(lock_path.read_text())['artifacts'])
        if len(dependencies) != 87:
            raise ValueError('dependency count drift')
        for path, digest in dependencies.items():
            if sha((cache/path).read_bytes()) != digest:
                raise ValueError('cache dependency identity drift: '+str(path))
        cp, plugin, receipt = helper.prepare_dependencies(ROOT, cache, route)
        (out/'dependency_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        report['dependency_receipt_sha256'] = sha((out/'dependency_receipt.json').read_bytes())
        if subprocess.check_output(['git', '-C', str(hardfloat), 'rev-parse', 'HEAD'], text=True).strip() != HARDFLOAT:
            raise ValueError('HardFloat head drift')
        hpaths = subprocess.check_output(['git', '-C', str(hardfloat), 'ls-tree', '-r', '--name-only', HARDFLOAT, '--', 'hardfloat/src/main/scala'], text=True).splitlines()
        hpaths = [p for p in hpaths if p.endswith('.scala')]
        if len(hpaths) != 20:
            raise ValueError('HardFloat source count drift')
        sources = [source/p for p in paths if p.endswith('.scala')]
        for path in hpaths:
            dest = source/'pinned_hardfloat'/path;dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(subprocess.check_output(['git', '-C', str(hardfloat), 'show', HARDFLOAT+':'+path]));sources.append(dest)
        sources += sorted((source/'baseline').glob('*.scala'))+[WINDOW/'FfnWindowElaboration.scala',TASK/'DrainElaboration.scala']
        report['source_sha256'] = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sources}
        report['hardfloat_commit'] = HARDFLOAT;report['typechecked_source_count'] = len(sources)
        if validate_only:
            report['status'] = 'PASS_SOURCE_AND_CACHE_VALIDATION_ONLY';save();return report
        java = ['java', '-Xmx1024m', '-XX:ActiveProcessorCount=1']
        classes = out/'classes';classes.mkdir()
        command(java+['-cp', cp, 'scala.tools.nsc.Main', '-classpath', cp, '-Xplugin:'+str(plugin), '-d', str(classes)]+list(map(str, sources)), 'compile.log')
        report['full_host_top_typechecked'] = True;report['full_qwen_owner_kernel_typechecked'] = True
        command(java+['-cp', str(classes)+':'+cp, 'heteronpu.continuous.DrainElaboration', str(out/'chirrtl')], 'elaboration.log')
        report.update(audit(out/'chirrtl', helper))
        for path in sources:
            if sha(path.read_bytes()) != report['source_sha256'][str(path.relative_to(ROOT))]:
                raise ValueError('source changed during compile')
        report['status'] = 'PASS_FFN_DRAIN_FULL_TYPECHECK_AND_FRONTEND_ONLY'
        report['wall_seconds'] = time.monotonic()-start;save();return report
    except Exception as error:
        report.update(status='FAILED', error=str(error), wall_seconds=time.monotonic()-start);save();raise


def replay_audit(evidence):
    """Replay the final auditor on immutable compiled sources/IR without Java."""
    receipt=evidence/'summary.json'
    previous=json.loads(receipt.read_text())
    if previous['status']!='PASS_FFN_DRAIN_FULL_TYPECHECK_AND_FRONTEND_ONLY':
        raise ValueError('successful frozen frontend receipt required')
    for path,digest in previous['source_sha256'].items():
        if sha((ROOT/path).read_bytes())!=digest: raise ValueError('compiled source drift: '+path)
    for name,info in previous['generated_chirrtl'].items():
        if sha((evidence/'chirrtl'/name).read_bytes())!=info['sha256']: raise ValueError('IR drift: '+name)
    helper_path=ROOT/'scripts/check_matrix_interface_candidate.py'
    route=json.loads(frozen('candidates/qwen2_resident_matrix/transposed_route/manifest.json'))
    if sha(helper_path.read_bytes())!=route['dependencies']['scripts/check_matrix_interface_candidate.py']:
        raise ValueError('dependency auditor identity drift')
    helper=module('window_replay_helper',helper_path)
    report=audit(evidence/'chirrtl',helper)
    report.update(status='PASS_FFN_DRAIN_AUDIT_REPLAY',source_receipt_sha256=sha(receipt.read_bytes()),
                  frontend_tool_sha256=sha(Path(__file__).read_bytes()),dependency_auditor_sha256=sha(helper_path.read_bytes()),java_invoked=False,
                  compiled_source_count=previous['typechecked_source_count'])
    target=evidence/'audit_replay.json'
    if target.exists(): raise ValueError('audit replay evidence already exists')
    target.write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--audit-existing', type=Path)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--hardfloat', type=Path)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    if args.audit_existing:
        result=replay_audit(args.audit_existing.resolve())
    else:
        if not all((args.out,args.cache,args.hardfloat)): parser.error('--out, --cache and --hardfloat are required for a new frontend run')
        result = run(args.out.resolve(), args.cache.resolve(), args.hardfloat.resolve(), args.validate_only)
    print(json.dumps({'status': result['status']}))
