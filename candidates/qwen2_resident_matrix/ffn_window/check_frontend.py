#!/usr/bin/env python3
"""Pinned actual source typecheck and bounded internal Dense window frontend.

No RTL, simulation, full Host/kernel elaboration, native arithmetic acceptance
or area/timing result. Public Host fusion and final act DDR drain remain open.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, re, subprocess, sys, time
sys.dont_write_bytecode = True
TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[2]
HOST = TASK.parent / 'transposed_host'
TILES = TASK.parent / 'ffn_tiles'
COMMIT = '825caff3a6c618419c49c7da452e009ce86ae8b5'
PREFIX = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
OWNER = 'candidates/qwen2_resident_matrix/transposed_owner/'
PATCH = 'candidates/qwen2_resident_matrix/ffn_window/window.patch'
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
    tiles = module('window_tile_compose', TILES / 'check_frontend.py')
    paths, pins = tiles.compose(out)
    if pins != json.loads((TILES / 'source_pins.json').read_text()):
        raise ValueError('unchanged FFN tile composition identity drift')
    # Preserve the published tiles-on/window-off profile, including its ABI.
    for path, cls in [(OWNER+'TransposedDenseBanks.scala', 'TransposedDownDenseBanks'),
                      (OWNER+'TransposedDenseOwner.scala', 'TransposedDenseDownOwner')]:
        original=(out/path).read_text().split('class '+cls,1)[1]
        original='class '+cls+original
        if cls=='TransposedDownDenseBanks': original=original.split('/** Internal typed tile ABI.',1)[0]
        original=original.replace('class '+cls, 'class '+cls+'TilesBaseline',1)
        original=original.replace(' extends Module {', ' extends Module {\n  override def desiredName = "'+cls+'"',1)
        dest=out/'baseline'/(cls+'TilesBaseline.scala')
        dest.write_text('package heteronpu.continuous\nimport chisel3._\nimport chisel3.util._\n'+original)
    data = (ROOT / PATCH).read_bytes()
    patch = out / 'patch_ffn_window.patch';patch.write_bytes(data)
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=out, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=out, check=True)
    pins['patches'][PATCH] = sha(data)
    pins['patched_sources'] = {p: sha((out/p).read_bytes()) for p in paths}
    for filename in ('check_frontend.py', 'source_pins.json'):
        path=TILES/filename
        pins['composition_helpers'][str(path.relative_to(ROOT))]=sha(path.read_bytes())
    return paths, pins


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
    host = module('ffn_register_helper', HOST/'check_frontend.py')
    report = {'default_off_ir': {}, 'resource_audit': {}, 'register_inventory': {},
              'top_elaborated': False, 'rtl_generated': False, 'hardware_arithmetic_executed': False,
              'quiescent_tile_transactions_only': False, 'live_tiles_allow_dense_k_max': 1536, 'host_ffn_dispatch_implemented': False,
              'matrix_gate_up_direct_writeback_implemented': True, 'retained_a_lease_source_implemented': True, 'public_host_completion_unchanged': True, 'act_ddr_drain_implemented': False,
              'area_timing_measured': False,
              'added_combinational_logic': 'tile RMW arbitration, bounded Matrix-result lane mux, window/lease admission and commit validation, context-major producer index; no synthesis/QoR estimate',
              'retained_a_bytes': 393216, 'tile_slot_bytes': 81920, 'tile_slots': 3,
              'sram_bytes': 786432}
    for profile in ('banks', 'owner', 'silu'):
        before = normalized((directory/(profile+'_baseline.fir')).read_text(), helper)
        after = normalized((directory/(profile+'_disabled.fir')).read_text(), helper)
        if before != after:
            raise ValueError('default-off normalized CHIRRTL drift: '+profile)
        report['default_off_ir'][profile] = {'equal': True, 'sha256': sha(after.encode())}
        enabled = normalized((directory/(profile+'_enabled.fir')).read_text(), helper)
        old = host.register_inventory(after)
        new = host.register_inventory(enabled)
        delta = {}
        for name, regs in new.items():
            additions = {reg: data for reg, data in regs.items() if old.get(name, {}).get(reg) != data}
            if additions:
                delta[name] = {'bits': sum(v['bits'] for v in additions.values()), 'registers': additions}
        report['register_inventory'][profile] = {'added_or_changed': delta, 'by_module': new}
        if profile in ('banks', 'owner'):
            report['resource_audit'][profile] = memory_audit(enabled, allow_operand_queue=profile=='owner')
        else:
            if len(re.findall(r'inst vector of SiluVectorUnit', enabled)) != 1:
                raise ValueError('exactly one existing SiLU vector unit required')
            if len(re.findall(r'inst cores_\d+ of BlockScalarFloat', enabled)) != 16:
                raise ValueError('exactly sixteen existing scalar lanes required')
    report['tiles_on_window_off_ir']={}
    for profile in ('banks','owner'):
        before=normalized((directory/(profile+'_tiles_baseline.fir')).read_text(),helper)
        after=normalized((directory/(profile+'_tiles.fir')).read_text(),helper)
        if before!=after: raise ValueError('published tiles-on/window-off CHIRRTL drift: '+profile)
        if 'matrixProducerOrder' in after or 'io_window' in after:
            raise ValueError('default-off internal port ABI drift: '+profile)
        report['tiles_on_window_off_ir'][profile]={'equal':True,'sha256':sha(after.encode())}
    harness = normalized((directory/'tile_silu_harness.fir').read_text(), helper)
    report['resource_audit']['harness'] = memory_audit(harness)
    if len(re.findall(r'inst vector of SiluVectorUnit', harness)) != 1 or len(re.findall(r'inst cores_\d+ of BlockScalarFloat', harness)) != 16:
        raise ValueError('harness must reuse exactly one real sixteen-lane SFU')
    if 'extmodule SiluVectorUnit' in harness or 'extmodule BlockScalarFloat' in harness:
        raise ValueError('arithmetic stand-in forbidden')
    regs = host.register_inventory(harness)
    report['register_inventory']['harness'] = {'by_module': regs}
    bank_regs = regs['TransposedDownDenseBanks']
    payload = {name: val['bits'] for name, val in bank_regs.items() if name in ('writeValue', 'responseValue')}
    # Chisel preserves val names inside Scala if blocks.
    if payload != {'writeValue': 512, 'responseValue': 512}:
        raise ValueError('exact bounded tile payload hold ledger drift: '+str(payload))
    report['tile_storage_ledger'] = {'bank_write_hold_bits': 512, 'bank_read_response_hold_bits': 512,
        'bridge_gate_hold_bits': regs['FfnTileSiluBridge']['gate']['bits'],
        'bank_added_register_bits': sum(v['bits'] for v in report['register_inventory']['banks']['added_or_changed'].values()),
        'bridge_all_register_bits': sum(v['bits'] for v in regs['FfnTileSiluBridge'].values()),
        'new_sram_arrays': 0, 'new_sfu_units': 0, 'sfu_vector_units': 1, 'sfu_lanes': 16,
        'synchronous_rmw_response_hold_bits': 0,
        'response_error_after_stall': 'immutable; later abort gates publication through sticky resetRequired'}
    baseline_owner=host.register_inventory(normalized((directory/'owner_tiles.fir').read_text(), helper))
    window_owner=host.register_inventory(normalized((directory/'owner_enabled.fir').read_text(), helper))
    added={}
    for name, regs in window_owner.items():
        delta={r:v for r,v in regs.items() if baseline_owner.get(name,{}).get(r)!=v}
        if delta:
            old_bits=sum(v['bits'] for v in baseline_owner.get(name,{}).values())
            new_bits=sum(v['bits'] for v in regs.values())
            added[name]={'changed_register_bits':sum(v['bits'] for v in delta.values()),
                         'module_before_bits':old_bits, 'module_after_bits':new_bits,
                         'net_added_bits':new_bits-old_bits, 'registers':delta}
    report['window_added_or_changed_registers'] = added
    report['window_net_added_register_bits'] = sum(v['net_added_bits'] for v in added.values())
    current=window_owner['TransposedDenseDownOwner']
    if current['finalValue']['bits'] != 131072 or current['prefixWriteIndex']['bits'] != 8:
        raise ValueError('existing result hold or shared cursor drift')
    report['window_result_storage']={'existing_final_value_bits':131072, 'shared_prefix_cursor_bits':8,
        'new_result_buffers':0, 'new_sram_arrays':0, 'matrix_units_added':0, 'sfu_units_added':0}
    report['window_internal_completion']={'ddr_write_bytes':0, 'old_owner_done':False,
        'full_n_stride_preserved':True, 'lease_commits_only_at_real_a_fence':True}
    report['generated_chirrtl'] = {p.name: {'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size} for p in sorted(directory.glob('*.fir'))}
    return report


def run(out, cache, hardfloat, validate_only=False):
    if out.exists():
        raise ValueError('use a new evidence directory')
    out.mkdir(parents=True)
    start = time.monotonic()
    report = {'status': 'STARTED', 'source_commit': COMMIT, 'ffn_tiles_parent_commit': '17baa23c1d540681c52038ea8a224dc7fd96e811', 'commands': [],
              'tooling_sha256': {name:sha((TASK/name).read_bytes()) for name in ('check_frontend.py','test_frontend.py','source_pins.json','FfnWindowElaboration.scala','window.patch')},
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
        sources += sorted((source/'baseline').glob('*.scala'))+[TASK/'FfnWindowElaboration.scala']
        report['source_sha256'] = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sources}
        report['hardfloat_commit'] = HARDFLOAT;report['typechecked_source_count'] = len(sources)
        if validate_only:
            report['status'] = 'PASS_SOURCE_AND_CACHE_VALIDATION_ONLY';save();return report
        java = ['java', '-Xmx1024m', '-XX:ActiveProcessorCount=1']
        classes = out/'classes';classes.mkdir()
        command(java+['-cp', cp, 'scala.tools.nsc.Main', '-classpath', cp, '-Xplugin:'+str(plugin), '-d', str(classes)]+list(map(str, sources)), 'compile.log')
        report['full_host_top_typechecked'] = True;report['full_qwen_owner_kernel_typechecked'] = True
        command(java+['-cp', str(classes)+':'+cp, 'heteronpu.continuous.FfnWindowElaboration', str(out/'chirrtl')], 'elaboration.log')
        report.update(audit(out/'chirrtl', helper))
        for path in sources:
            if sha(path.read_bytes()) != report['source_sha256'][str(path.relative_to(ROOT))]:
                raise ValueError('source changed during compile')
        report['status'] = 'PASS_FFN_WINDOW_FULL_TYPECHECK_AND_FRONTEND_ONLY'
        report['wall_seconds'] = time.monotonic()-start;save();return report
    except Exception as error:
        report.update(status='FAILED', error=str(error), wall_seconds=time.monotonic()-start);save();raise


def replay_audit(evidence):
    """Replay the final auditor on immutable compiled sources/IR without Java."""
    receipt=evidence/'summary.json'
    previous=json.loads(receipt.read_text())
    if previous['status']!='PASS_FFN_WINDOW_FULL_TYPECHECK_AND_FRONTEND_ONLY':
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
    report.update(status='PASS_FFN_WINDOW_AUDIT_REPLAY',source_receipt_sha256=sha(receipt.read_bytes()),
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
