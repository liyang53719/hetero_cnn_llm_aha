#!/usr/bin/env python3
"""Pinned actual source typecheck and bounded tile/SFU CHIRRTL only.

No RTL, simulation, complete Host/Kernel elaboration, native arithmetic
acceptance or area/timing result. Tile borrowing remains quiescent-only; live tiles coexist with Dense K<=1536.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, re, subprocess, sys, time
sys.dont_write_bytecode = True
TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[2]
HOST = TASK.parent / 'transposed_host'
COMMIT = '825caff3a6c618419c49c7da452e009ce86ae8b5'
PREFIX = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
OWNER = 'candidates/qwen2_resident_matrix/transposed_owner/'
PATCH = 'candidates/qwen2_resident_matrix/ffn_tiles/tile_ports.patch'
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
    host = module('ffn_host_compose', HOST / 'check_frontend.py')
    paths, pins = host.compose(out)
    if pins != json.loads((HOST / 'source_pins.json').read_text()):
        raise ValueError('unchanged Host composition identity drift')
    # Preserve exact preimages for default-off elaboration comparisons.
    for path, cls in [(OWNER+'TransposedDenseBanks.scala', 'TransposedDownDenseBanks'),
                      (OWNER+'TransposedDenseOwner.scala', 'TransposedDenseDownOwner'),
                      (PREFIX+'VectorSilu.scala', 'VectorSiluOwner')]:
        original = (out / path).read_text()
        start = original.index('class ' + cls)
        original = original[start:]
        # These three classes are the final declarations in their source files.
        decl = re.search(r'class '+cls+r'(?:\([^\n]*\))? extends Module \{', original)
        if decl is None:
            raise ValueError('baseline declaration drift: '+cls)
        original = original[:decl.start()] + decl.group(0).replace(cls, cls+'Baseline', 1) + original[decl.end():]
        marker = ' extends Module {\n'
        original = original.replace(marker, marker+'  override def desiredName = "'+cls+'"\n', 1)
        dest = out / 'baseline' / (cls+'Baseline.scala')
        dest.parent.mkdir(exist_ok=True)
        dest.write_text('package heteronpu.continuous\nimport chisel3._\nimport chisel3.util._\n'+original)
    data = (ROOT / PATCH).read_bytes()
    patch = out / 'patch_ffn_tiles.patch'
    patch.write_bytes(data)
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=out, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=out, check=True)
    pins['patches'][PATCH] = sha(data)
    pins['patched_sources'] = {p: sha((out/p).read_bytes()) for p in paths}
    pins['composition_helpers'][str((HOST/'check_frontend.py').relative_to(ROOT))] = sha((HOST/'check_frontend.py').read_bytes())
    pins['composition_helpers'][str((HOST/'source_pins.json').relative_to(ROOT))] = sha((HOST/'source_pins.json').read_bytes())
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
              'quiescent_tile_transactions_only': True, 'live_tiles_allow_dense_k_max': 1536, 'host_ffn_dispatch_implemented': False,
              'matrix_gate_up_direct_writeback_implemented': False,
              'area_timing_measured': False,
              'added_combinational_logic': 'tile arbitration, tag/count validation, variable cols division/remainder address mapping, 16-lane finite-value checks, 16x8 FP32 read selection and RMW lane muxes; no synthesis/QoR estimate',
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
    report['generated_chirrtl'] = {p.name: {'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size} for p in sorted(directory.glob('*.fir'))}
    return report


def run(out, cache, hardfloat, validate_only=False):
    if out.exists():
        raise ValueError('use a new evidence directory')
    out.mkdir(parents=True)
    start = time.monotonic()
    report = {'status': 'STARTED', 'source_commit': COMMIT, 'commands': [],
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
        sources += sorted((source/'baseline').glob('*.scala'))+[TASK/'FfnTileElaboration.scala']
        report['source_sha256'] = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sources}
        report['hardfloat_commit'] = HARDFLOAT;report['typechecked_source_count'] = len(sources)
        if validate_only:
            report['status'] = 'PASS_SOURCE_AND_CACHE_VALIDATION_ONLY';save();return report
        java = ['java', '-Xmx1024m', '-XX:ActiveProcessorCount=1']
        classes = out/'classes';classes.mkdir()
        command(java+['-cp', cp, 'scala.tools.nsc.Main', '-classpath', cp, '-Xplugin:'+str(plugin), '-d', str(classes)]+list(map(str, sources)), 'compile.log')
        report['full_host_top_typechecked'] = True;report['full_qwen_owner_kernel_typechecked'] = True
        command(java+['-cp', str(classes)+':'+cp, 'heteronpu.continuous.FfnTileElaboration', str(out/'chirrtl')], 'elaboration.log')
        report.update(audit(out/'chirrtl', helper))
        for path in sources:
            if sha(path.read_bytes()) != report['source_sha256'][str(path.relative_to(ROOT))]:
                raise ValueError('source changed during compile')
        report['status'] = 'PASS_FFN_TILE_FULL_TYPECHECK_AND_FRONTEND_ONLY'
        report['wall_seconds'] = time.monotonic()-start;save();return report
    except Exception as error:
        report.update(status='FAILED', error=str(error), wall_seconds=time.monotonic()-start);save();raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--hardfloat', type=Path, required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    result = run(args.out.resolve(), args.cache.resolve(), args.hardfloat.resolve(), args.validate_only)
    print(json.dumps({'status': result['status']}))
