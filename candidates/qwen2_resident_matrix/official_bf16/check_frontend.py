#!/usr/bin/env python3
"""Pinned full Scala typecheck and bounded official BF16 CHIRRTL frontend gate.

No RTL, firtool, simulator, full Matrix/Host/core elaboration or numerical signoff.
Default-vs-explicit-Legacy equivalence is exact after diagnostic normalization.
Prepatch leaf comparisons are reported separately, without semantic equivalence
claims when unoptimized IR differs. The parent Host uses the new job bundle.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[2]
COMMIT = 'c761ec824ce2c027a66c22feb4a2154829f9d545'
HARDFLOAT = 'c1105e6ac6a0dd90fc80893efc4830ab609005d3'
PREFIX = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
PROFILES = tuple(f'{leaf}_{mode}' for leaf in ('host', 'silu', 'elementwise')
                 for mode in ('parent', 'default', 'legacy', 'official'))
JAVA = ['java', '-Xmx1024m', '-XX:ActiveProcessorCount=1']
TIMEOUT = 180


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def frozen(path):
    return subprocess.check_output(['git', 'show', COMMIT + ':' + path], cwd=ROOT)


def normalized(fir, helper):
    return re.sub(r'(?<= at )[A-Za-z_0-9]+\.scala:\d+ ', '<source> ',
                  helper.normalized_chirrtl(fir))


def parent_baselines(out, before, helper):
    """Rename actual prepatch classes only; keep the compiled dependency graph."""
    result = []
    for filename, name in (('HostBlockCommands.scala', 'HostBlockCommands'),
                           ('VectorSilu.scala', 'SiluVectorUnit'),
                           ('ElementwiseMemoryEngine.scala', 'ElementwiseMemoryEngine')):
        original = before[PREFIX + filename]
        imports = '\n'.join(x for x in original.splitlines()
                            if x.startswith(('package ', 'import '))) + '\n'
        body = helper.declaration(original, name)
        body = body.replace('class ' + name, 'class ' + name + 'OfficialParent', 1)
        body = body.replace(' extends Module {', ' extends Module {\n  override def desiredName = "' + name + '"', 1)
        target = out / 'official_parent' / (name + 'OfficialParent.scala')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(imports + body + '\n')
        result.append(target)
    return result


def resource_inventory(fir, register_helper):
    """Declared frontend registers, instances and memories, not physical QoR."""
    registers = register_helper.register_inventory(fir)
    modules = list(re.finditer(r'^  module (\w+) :.*?(?=^  (?:extmodule|module) |\Z)', fir, re.M | re.S))
    instances, memories = {}, {}
    for match in modules:
        name, body = match.group(1), match.group(0)
        instances[name] = dict(re.findall(r'^\s*inst (\w+) of (\w+)', body, re.M))
        memories[name] = {}
        for kind, mem, typ, depth in re.findall(r'^\s*(smem|cmem) (\w+) : (.*?)\s*\[(\d+)\]', body, re.M):
            # Preserve the declaration verbatim; Vec payloads have more than one dimension.
            line = next(x.strip() for x in body.splitlines() if re.match(r'\s*' + kind + ' ' + mem + r' :', x))
            ports = {p: len(re.findall(r'^\s*' + p + r' mport \w+ = ' + mem + r'\[', body, re.M)) for p in ('read', 'write', 'rdwr')}
            memories[name][mem] = {'declaration': line, 'ports': ports}
    require(not re.search(r'^  extmodule ', fir, re.M), 'unexpected opaque blackbox in bounded frontend')
    root = re.search(r'^circuit (\w+) :', fir, re.M)
    require(root is not None, 'missing CHIRRTL circuit')
    def total(name, active=()):
        require(name in registers and name not in active, 'unknown or recursive module: ' + name)
        return sum(x['bits'] for x in registers[name].values()) + sum(
            total(child, active + (name,)) for child in instances[name].values())
    return {'registers_by_module': registers, 'instances_by_module': instances,
            'memories_by_module': memories, 'hierarchical_register_bits': total(root[1])}


def audit(directory, helper, register_helper):
    report = {'default_equals_explicit_legacy': {}, 'prepatch_leaf_comparison': {},
              'resources': {}, 'enabled_register_delta': {},
              'rtl_generated': False, 'hardware_arithmetic_executed': False,
              'numerical_acceptance': False, 'qor_measured': False,
              'full_host_top_elaborated': False, 'full_qwen_owner_kernel_elaborated': False,
              'full_qwen2_core_elaborated': False, 'full_matrix_elaborated': False,
              'frontend_profiles': list(PROFILES)}
    normalized_ir = {name: normalized((directory / (name + '.fir')).read_text(), helper) for name in PROFILES}
    for name, fir in normalized_ir.items():
        report['resources'][name] = resource_inventory(fir, register_helper)
    for leaf in ('host', 'silu', 'elementwise'):
        default, legacy, official, parent = (normalized_ir[leaf + '_' + mode] for mode in ('default', 'legacy', 'official', 'parent'))
        require(default == legacy, 'default differs from explicit LegacyV0: ' + leaf)
        require(default != official, 'enabled policy has no CHIRRTL effect: ' + leaf)
        report['default_equals_explicit_legacy'][leaf] = {'equal': True, 'sha256': sha(default.encode())}
        report['prepatch_leaf_comparison'][leaf] = {
            'equal': parent == default, 'parent_sha256': sha(parent.encode()),
            'default_sha256': sha(default.encode()),
            'dependency_graph': 'same composed candidate; parent Host therefore includes the new internal job bit',
            'semantic_equivalence_proved_if_ir_differs': False}
        old, new = (report['resources'][leaf + '_' + mode] for mode in ('default', 'official'))
        require(old['instances_by_module'] == new['instances_by_module'], 'arithmetic/module duplication: ' + leaf)
        require(old['memories_by_module'] == new['memories_by_module'], 'SRAM declaration/port drift: ' + leaf)
        delta = new['hierarchical_register_bits'] - old['hierarchical_register_bits']
        report['enabled_register_delta'][leaf] = delta
        require(delta == (1424 if leaf == 'host' else 0), 'unexpected enabled register delta: ' + leaf)
        count = sum(len(x) for x in new['memories_by_module'].values())
        require(count == (16 if leaf == 'elementwise' else 0), 'unexpected bounded memory count: ' + leaf)
        if leaf != 'host':
            require(old['registers_by_module'] == new['registers_by_module'], 'leaf register inventory drift: ' + leaf)
    host = report['resources']['host_official']['registers_by_module']['HostBlockCommands']
    require({k: host[k]['bits'] for k in ('officialOutputs', 'officialHidden', 'officialRows')} ==
            {'officialOutputs': 1344, 'officialHidden': 64, 'officialRows': 16}, 'official provenance metadata ledger drift')
    report['scope'] = {'host': 'actual parser, resident enabled, 21 commands, 32 events; no job transactions executed',
                       'silu': 'actual production SiluVectorUnit, one of the supported 1..16 lanes',
                       'elementwise': 'actual 16-ALU engine, 32-element tiles, 16 banks x 2 rows x 128 bits (512 bytes)',
                       'register_ledger': 'CHIRRTL declared bits including hierarchy multiplicity; not synthesized area',
                       'unelaborated_source_only': 'full Host/kernel/core/Matrix, Dense owner and RMS datapath; enabled integration wiring source-audited and typechecked only'}
    report['generated_chirrtl'] = {p.name: {'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size}
                                  for p in sorted(directory.glob('*.fir'))}
    require(set(report['generated_chirrtl']) == {p + '.fir' for p in PROFILES}, 'unexpected/missing IR targets')
    return report


def run(out, cache, hardfloat, validate_only=False):
    require(not out.exists(), 'use a new evidence directory')
    out.mkdir(parents=True)
    start = time.monotonic()
    tooling = ('check_frontend.py', 'OfficialBf16Elaboration.scala', 'test_frontend.py',
               'chisel_policy.py', 'chisel_policy.patch')
    report = {'status': 'STARTED', 'source_commit': COMMIT, 'commands': [],
              'tooling_sha256': {n: sha((TASK / n).read_bytes()) for n in tooling},
              'java_budget': {'active_processors': 1, 'heap_mib': 1024, 'timeout_seconds_per_command': TIMEOUT},
              'full_production_source_typechecked': False, 'rtl_generated': False,
              'hardware_arithmetic_executed': False, 'numerical_acceptance': False}
    def save():
        (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    def command(argv, name):
        then = time.monotonic()
        entry = {'argv': argv, 'log': name, 'status': 'RUNNING', 'exit_code': None}
        report['commands'].append(entry); save()
        try:
            with (out / name).open('w') as log:
                result = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=TIMEOUT)
            entry.update(status='FINISHED', exit_code=result.returncode)
            require(result.returncode == 0, 'command failed: ' + name)
        except subprocess.TimeoutExpired:
            entry.update(status='TIMEOUT', timeout_seconds=TIMEOUT)
            raise
        finally:
            entry['wall_seconds'] = time.monotonic() - then; save()
    try:
        policy = module('official_policy_frontend', TASK / 'chisel_policy.py')
        source = out / 'source'
        # git apply is relative to a discovered repository prefix. The parent
        # composer must run outside this working tree, then verified postimages
        # are copied into the immutable evidence tree before any compilation.
        with tempfile.TemporaryDirectory(prefix='official_bf16_frontend_', dir='/tmp') as temporary:
            assembled = Path(temporary) / 'source'
            paths, source_audit, before, after = policy.compose(assembled)
            shutil.copytree(assembled, source)
        source_audit['source_assembly'] = str(source)
        for path, digest in source_audit['assembled_source_sha256'].items():
            require(sha((source / path).read_bytes()) == digest, 'copied source identity drift: ' + path)
        require(len(paths) == 72 and len(set(paths)) == 72 and sum(p.endswith('.scala') for p in paths) == 66, 'production source count drift')
        report['source_audit'] = source_audit
        report['production_source_count'] = len(paths)
        report['production_scala_source_count'] = 66
        report['existing_sv_sources_preserved_but_not_compiled'] = [p for p in paths if not p.endswith('.scala')]
        route = json.loads(frozen('candidates/qwen2_resident_matrix/transposed_route/manifest.json'))
        helper_path = ROOT / 'scripts/check_matrix_interface_candidate.py'
        require(sha(helper_path.read_bytes()) == route['dependencies']['scripts/check_matrix_interface_candidate.py'], 'dependency helper drift')
        helper = module('official_dependency_helper', helper_path)
        register_path = TASK.parent / 'transposed_host/check_frontend.py'
        register_helper = module('official_register_helper', register_path)
        report['auditor_sha256'] = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in (helper_path, register_path)}
        lock_path = ROOT / 'chisel/rope_hardware_oracle/maven-lock.json'
        require(sha(lock_path.read_bytes()) == route['maven_lock_sha256'], 'Maven lock drift')
        dependencies = helper.dependency_paths(json.loads(lock_path.read_text())['artifacts'])
        require(len(dependencies) == 87, 'dependency count drift')
        for path, digest in dependencies.items():
            require(sha((cache / path).read_bytes()) == digest, 'cache dependency identity drift: ' + path)
        cp, plugin, receipt = helper.prepare_dependencies(ROOT, cache, route)
        (out / 'dependency_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        report['dependency_receipt_sha256'] = sha((out / 'dependency_receipt.json').read_bytes())
        report['hardfloat_commit'] = HARDFLOAT
        require(subprocess.check_output(['git', '-C', str(hardfloat), 'rev-parse', 'HEAD'], text=True).strip() == HARDFLOAT, 'HardFloat head drift')
        hpaths = subprocess.check_output(['git', '-C', str(hardfloat), 'ls-tree', '-r', '--name-only', HARDFLOAT, '--', 'hardfloat/src/main/scala'], text=True).splitlines()
        hpaths = [p for p in hpaths if p.endswith('.scala')]
        require(len(hpaths) == 20, 'HardFloat source count drift')
        sources = [source / p for p in paths if p.endswith('.scala')]
        for path in hpaths:
            target = source / 'pinned_hardfloat' / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(['git', '-C', str(hardfloat), 'show', HARDFLOAT + ':' + path]))
            sources.append(target)
        sources += parent_baselines(source, before, helper)
        harness = source / 'OfficialBf16Elaboration.scala'
        harness.write_bytes((TASK / harness.name).read_bytes()); sources.append(harness)
        report['source_sha256'] = {str(p.relative_to(out)): sha(p.read_bytes()) for p in sources + [source / p for p in paths]}
        report['compiler_sources'] = [str(p.relative_to(out)) for p in sources]
        report['compiler_source_count'] = len(sources)
        if validate_only:
            report['status'] = 'PASS_SOURCE_AND_CACHE_VALIDATION_ONLY'; save(); return report
        classes = out / 'classes'; classes.mkdir()
        command(JAVA + ['-cp', cp, 'scala.tools.nsc.Main', '-classpath', cp, '-Xplugin:' + str(plugin), '-d', str(classes)] + list(map(str, sources)), 'compile.log')
        report['full_production_source_typechecked'] = True
        for profile in PROFILES:
            command(JAVA + ['-cp', str(classes) + ':' + cp, 'heteronpu.continuous.OfficialBf16Elaboration', str(out / 'chirrtl'), profile], profile + '.log')
        report.update(audit(out / 'chirrtl', helper, register_helper))
        for path, digest in report['source_sha256'].items():
            require(sha((out / path).read_bytes()) == digest, 'compiled source changed: ' + path)
        for name, digest in report['tooling_sha256'].items():
            require(sha((TASK / name).read_bytes()) == digest, 'tooling changed during compile: ' + name)
        for path, digest in report['auditor_sha256'].items():
            require(sha((ROOT / path).read_bytes()) == digest, 'auditor changed during compile: ' + path)
        report['status'] = 'PASS_OFFICIAL_BF16_TYPECHECK_AND_BOUNDED_FRONTEND_ONLY'
        report['wall_seconds'] = time.monotonic() - start; save(); return report
    except Exception as error:
        report.update(status='FAILED', error=str(error), wall_seconds=time.monotonic() - start)
        save(); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--hardfloat', type=Path, required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    result = run(args.out.resolve(), args.cache.resolve(), args.hardfloat.resolve(), args.validate_only)
    print(json.dumps({'status': result['status']}))
