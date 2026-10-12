#!/usr/bin/env python3
"""Pinned actual source typecheck and bounded production resident FFN coordinator and Host frontend.

No RTL, simulation, full Host top/kernel elaboration, native arithmetic acceptance
or area/timing result. Real Host parser and coordinator are bounded frontend targets.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, re, subprocess, sys, time
sys.dont_write_bytecode = True
TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[2]
HOST = TASK.parent / 'transposed_host'
WINDOW = TASK.parent / 'ffn_window'
DRAIN = TASK.parent / 'ffn_drain'
COMMIT = 'c761ec824ce2c027a66c22feb4a2154829f9d545'
PREFIX = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
OWNER = 'candidates/qwen2_resident_matrix/transposed_owner/'
PATCH = 'candidates/qwen2_resident_matrix/ffn_group/group.patch'
MODULES = ('FfnTileSiluBridge.scala','FfnResidentCoordinator.scala','FfnResidentProfile.scala')
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
    drain=module('group_drain_compose',DRAIN/'check_frontend.py')
    paths,pins=drain.compose(out)
    if pins!=json.loads((DRAIN/'source_pins.json').read_text()):
        raise ValueError('unchanged FFN drain composition identity drift')
    old=(out/(PREFIX+'HostBlockCommands.scala')).read_text()
    old=old.replace('class HostBlockCommands(', 'class HostBlockCommandsGroupBaseline(',1)
    old=old.replace(' extends Module {', ' extends Module {\n  override def desiredName = "HostBlockCommands"',1)
    (out/'baseline'/'HostBlockCommandsGroupBaseline.scala').write_text(old)
    old=(WINDOW/'FfnWindowElaboration.scala').read_text()
    old=old[old.index('class FfnTileSiluBridge extends Module'):old.index('/** Only the bank service')]
    old=old.replace('class FfnTileSiluBridge extends Module {', 'class FfnTileSiluBridgeBaseline extends Module {\n  override def desiredName = "FfnTileSiluBridge"',1)
    (out/'baseline'/'FfnTileSiluBridgeBaseline.scala').write_text('package heteronpu.continuous\nimport chisel3._\nimport chisel3.util._\n'+old)
    data=(ROOT/PATCH).read_bytes();patch=out/'patch_ffn_group.patch';patch.write_bytes(data)
    subprocess.run(['git','apply','--check',str(patch)],cwd=out,check=True)
    subprocess.run(['git','apply',str(patch)],cwd=out,check=True)
    for name in MODULES:
        rel=str((TASK/name).relative_to(ROOT));dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes((TASK/name).read_bytes());paths.append(rel)
    pins['patches'][PATCH]=sha(data)
    pins['patched_sources']={p:sha((out/p).read_bytes()) for p in paths}
    for name in ('check_frontend.py','source_pins.json','drain.patch'):
        path=DRAIN/name;pins['composition_helpers'][str(path.relative_to(ROOT))]=sha(path.read_bytes())
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
    register=module('group_register_helper',HOST/'check_frontend.py')
    report={'default_off_ir':{},'register_inventory':{},'full_host_top_elaborated':False,
      'full_qwen_owner_kernel_elaborated':False,'host_parser_elaborated':True,'coordinator_elaborated':True,
      'top_elaborated':False,'rtl_generated':False,'hardware_arithmetic_executed':False,
      'host_ffn_dispatch_implemented':True,'act_ddr_drain_implemented':True,
      'numeric_policy_approved':False,'native_arithmetic_accepted':False,'fp32_final_accepted':False,
      'measured_performance':False,'area_timing_measured':False}
    for profile in ('bridge','host'):
        old=normalized((directory/(profile+'_baseline.fir')).read_text(),helper)
        new=normalized((directory/(profile+'_disabled.fir')).read_text(),helper)
        if old!=new:raise ValueError('default-off normalized CHIRRTL drift: '+profile)
        report['default_off_ir'][profile]={'equal':True,'sha256':sha(new.encode())}
    for profile in ('coordinator','host_enabled'):
        fir=normalized((directory/(profile+'.fir')).read_text(),helper)
        if re.search(r'^\s*(?:s|c)mem ',fir,re.M):raise ValueError('new memory in metadata controller')
        if re.search(r'inst .* of (?:SiluVectorUnit|BlockScalarFloat|MatrixPipelineService)',fir):
            raise ValueError('controller duplicates arithmetic resource')
        report['register_inventory'][profile]=register.register_inventory(fir)
    regs=report['register_inventory']['coordinator']
    if regs['FfnTileSiluBridge']['gate']['bits']!=512:raise ValueError('original 512-bit gate hold drift')
    old=register.register_inventory(normalized((directory/'host_disabled.fir').read_text(),helper))
    new=report['register_inventory']['host_enabled']
    report['host_metadata_added_bits']=sum(v['bits'] for d in new.values() for v in d.values())-sum(v['bits'] for d in old.values() for v in d.values())
    report['coordinator_register_bits']=sum(v['bits'] for v in regs['FfnResidentCoordinator'].values())
    report['group_increment_register_ledger']={
      'comparison_base':'already drain/window/tile-enabled kernel with external tile/SFU ports, before resident coordinator',
      'coordinator_metadata_bits':report['coordinator_register_bits'],
      'host_metadata_added_bits':report['host_metadata_added_bits'],
      'migrated_bridge_total_register_bits':sum(v['bits'] for v in regs['FfnTileSiluBridge'].values()),
      'migrated_bridge_gate_payload_hold_bits':512,
      'kernel_registered_shared_poison_bits_source_only':1,
      'top_registered_memory_poison_bits_source_only':1,
      'group_increment_total_bits_including_source_only_poison':report['coordinator_register_bits']+report['host_metadata_added_bits']+sum(v['bits'] for v in regs['FfnTileSiluBridge'].values())+2,
      'new_payload_holds_beyond_migrated_bridge':0,'new_result_buffers':0,
      'bridge_was_previously_harness_only':True,
      'kernel_and_top_full_elaboration_performed':False,
      'prior_candidate_bank_owner_loan_deltas':'unchanged; accounted in parent window/drain receipts'}
    report['contract']={'public_opcodes':[32,32,53],'virtual_gate_up':True,'whole_launch_root_preflight':True,
      'all_three_original_completions_delayed':True,'act_only_ddr_publication':True,
      'gate_up_weights':'BF16','a_act':'FP32','shape_m':[16,128],'shape_k':1536,'shape_n':8960,
      'groups':56,'tile_columns':160,'act_bytes_m16':573440,'act_bytes_m128':4587520,
      'normal_down_uses_ddr':True,'cycles':'actual accept-to-first-terminal wall edges; excludes stalled terminal',
      'macs':'actual owner terminal counters, including error/drain terminals; never shape predictions',
      'new_sram_arrays':0,'new_matrix_units':0,'new_sfu_units':0,'new_dma_instances':0}
    report['generated_chirrtl']={p.name:{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in sorted(directory.glob('*.fir'))}
    return report


def run(out, cache, hardfloat, validate_only=False):
    if out.exists():
        raise ValueError('use a new evidence directory')
    out.mkdir(parents=True)
    start = time.monotonic()
    report = {'status': 'STARTED', 'source_commit': COMMIT, 'ffn_drain_parent_composition':'exact source_pins.json', 'commands': [],
              'tooling_sha256': {name:sha((TASK/name).read_bytes()) for name in ('check_frontend.py','source_pins.json','FfnGroupElaboration.scala','group.patch')+MODULES},
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
        sources += sorted((source/'baseline').glob('*.scala'))+[TASK/'FfnGroupElaboration.scala']
        report['source_sha256'] = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sources}
        report['hardfloat_commit'] = HARDFLOAT;report['typechecked_source_count'] = len(sources)
        if validate_only:
            report['status'] = 'PASS_SOURCE_AND_CACHE_VALIDATION_ONLY';save();return report
        java = ['java', '-Xmx1024m', '-XX:ActiveProcessorCount=1']
        classes = out/'classes';classes.mkdir()
        command(java+['-cp', cp, 'scala.tools.nsc.Main', '-classpath', cp, '-Xplugin:'+str(plugin), '-d', str(classes)]+list(map(str, sources)), 'compile.log')
        report['full_host_top_typechecked'] = True;report['full_qwen_owner_kernel_typechecked'] = True
        command(java+['-cp', str(classes)+':'+cp, 'heteronpu.continuous.FfnGroupElaboration', str(out/'chirrtl')], 'elaboration.log')
        report.update(audit(out/'chirrtl', helper))
        for path in sources:
            if sha(path.read_bytes()) != report['source_sha256'][str(path.relative_to(ROOT))]:
                raise ValueError('source changed during compile')
        report['status'] = 'PASS_FFN_GROUP_FULL_TYPECHECK_AND_FRONTEND_ONLY'
        report['wall_seconds'] = time.monotonic()-start;save();return report
    except Exception as error:
        report.update(status='FAILED', error=str(error), wall_seconds=time.monotonic()-start);save();raise


def replay_audit(evidence):
    """Replay the final auditor on immutable compiled sources/IR without Java."""
    receipt=evidence/'summary.json'
    previous=json.loads(receipt.read_text())
    if previous['status']!='PASS_FFN_GROUP_FULL_TYPECHECK_AND_FRONTEND_ONLY':
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
    report.update(status='PASS_FFN_GROUP_AUDIT_REPLAY',source_receipt_sha256=sha(receipt.read_bytes()),
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
